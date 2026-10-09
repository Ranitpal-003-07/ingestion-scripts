package main

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
	smithyhttp "github.com/aws/smithy-go/transport/http"
)

const (
	defaultRegion     = "ap-south-1"
	defaultRetryDelay = 5 * time.Second
)

func main() {
	loadEnvFile(".env")

	ctx := context.Background()

	shutdown, err := initTracer(ctx)
	if err != nil {
		log.Fatalf("failed to initialize tracer: %v", err)
	}
	defer func() {
		shutdownCtx := context.Background()
		if err := shutdown(shutdownCtx); err != nil {
			log.Printf("error shutting down tracer: %v", err)
		}
	}()

	sourceRegion := envOr("S3_SOURCE_REGION", envOr("AWS_REGION", defaultRegion))
	defaultDestRegion := envOr("S3_DEST_REGION", envOr("AWS_REGION", sourceRegion))
	sourceBucket := os.Getenv("S3_SOURCE_BUCKET")
	destBuckets := parseCSV(envOr("S3_DEST_BUCKETS", os.Getenv("S3_DEST_BUCKET")))
	destRegions := parseCSV(os.Getenv("S3_DEST_REGIONS"))
	prefix := os.Getenv("S3_PREFIX")
	destPrefixes := parseCSV(envOr("S3_DEST_PREFIXES", os.Getenv("S3_DEST_PREFIX")))
	workers := envInt("S3_COPY_WORKERS", 10)
	batchSize := envInt("S3_BATCH_SIZE", 10)
	batchInterval := envDuration("S3_BATCH_INTERVAL", 0)
	retryDelay := envDuration("S3_RETRY_DELAY", defaultRetryDelay)
	if workers < 1 {
		workers = 1
	}
	if batchSize < 1 {
		batchSize = 1
	}

	if sourceBucket == "" {
		log.Fatal("S3_SOURCE_BUCKET is required (set in .env or env)")
	}
	if len(destBuckets) == 0 {
		log.Fatal("S3_DEST_BUCKET or S3_DEST_BUCKETS is required (set in .env or env)")
	}
	if len(destRegions) > 0 && len(destRegions) != len(destBuckets) {
		log.Fatalf("S3_DEST_REGIONS has %d entries but S3_DEST_BUCKET(S) has %d — counts must match (or omit S3_DEST_REGIONS to use S3_DEST_REGION for all)",
			len(destRegions), len(destBuckets))
	}
	if len(destPrefixes) > 1 && len(destPrefixes) != len(destBuckets) {
		log.Fatalf("S3_DEST_PREFIX(ES) has %d entries but S3_DEST_BUCKET(S) has %d — use one shared prefix or one per bucket",
			len(destPrefixes), len(destBuckets))
	}

	sourceClient, err := newS3Client(ctx, sourceRegion)
	if err != nil {
		log.Fatalf("load AWS config (source region %s): %v", sourceRegion, err)
	}

	dests := make([]destTarget, 0, len(destBuckets))
	clientByRegion := map[string]*s3.Client{}
	for i, bucket := range destBuckets {
		region := defaultDestRegion
		if len(destRegions) > 0 {
			region = destRegions[i]
		}
		prefixForDest := ""
		switch {
		case len(destPrefixes) == 1:
			prefixForDest = destPrefixes[0]
		case len(destPrefixes) > 1:
			prefixForDest = destPrefixes[i]
		}
		client, ok := clientByRegion[region]
		if !ok {
			client, err = newS3Client(ctx, region)
			if err != nil {
				log.Fatalf("load AWS config (dest region %s): %v", region, err)
			}
			clientByRegion[region] = client
		}
		dests = append(dests, destTarget{
			bucket: bucket,
			region: region,
			prefix: prefixForDest,
			client: client,
		})
	}

	destSummary := formatDests(dests)
	log.Printf("copy s3://%s (%s) -> %s (prefix=%q, workers=%d, batch_size=%d, batch_interval=%s)",
		sourceBucket, sourceRegion, destSummary, prefix, workers, batchSize, batchInterval)

	listStart := time.Now()
	keys, err := listKeysWithRetry(ctx, sourceClient, sourceBucket, prefix, retryDelay)
	if err != nil {
		log.Fatalf("ListObjectsV2 stopped: %v", err)
	}
	listElapsed := time.Since(listStart)
	listStatus := 200

	fmt.Println("\n--- list ---")
	fmt.Printf("source:        s3://%s\n", sourceBucket)
	fmt.Printf("source_region: %s\n", sourceRegion)
	fmt.Printf("dests:         %d\n", len(dests))
	for i, d := range dests {
		fmt.Printf("  dest[%d]:     s3://%s (%s) dest_prefix=%q\n", i, d.bucket, d.region, d.prefix)
	}
	fmt.Printf("prefix:        %q\n", prefix)
	fmt.Printf("workers:       %d\n", workers)
	fmt.Printf("batch_size:    %d\n", batchSize)
	fmt.Printf("batch_interval:%s\n", batchInterval)
	fmt.Printf("http_status:   %d\n", listStatus)
	fmt.Printf("objects:     %d\n", len(keys))
	fmt.Printf("elapsed:     %s\n", listElapsed)

	if len(keys) == 0 {
		log.Println("source bucket/prefix is empty — nothing to copy")
		return
	}

	copyStart := time.Now()
	var totalCopied, totalFailed, totalBytes atomic.Int64

	batches := chunkKeys(keys, batchSize)
	for i, batch := range batches {
		batchNum := i + 1
		log.Printf("BATCH START batch=%d/%d files=%d dests=%d", batchNum, len(batches), len(batch), len(dests))

		batchStart := time.Now()
		copied, failed, bytes := runBatch(ctx, sourceClient, dests, workers,
			sourceBucket, batch, retryDelay)

		batchElapsed := time.Since(batchStart)
		totalCopied.Add(copied)
		totalFailed.Add(failed)
		totalBytes.Add(bytes)

		rate := filesPerSec(copied, batchElapsed)
		log.Printf("BATCH DONE  batch=%d/%d sent=%d failed=%d bytes=%d elapsed=%s rate=%.2f files/s",
			batchNum, len(batches), copied, failed, bytes, batchElapsed, rate)

		fmt.Printf("\n--- batch %d/%d ---\n", batchNum, len(batches))
		fmt.Printf("sent:     %d\n", copied)
		fmt.Printf("failed:   %d\n", failed)
		fmt.Printf("bytes:    %d\n", bytes)
		fmt.Printf("elapsed:  %s\n", batchElapsed)
		fmt.Printf("rate:     %.2f files/s\n", rate)

		if batchNum < len(batches) && batchInterval > 0 {
			log.Printf("BATCH WAIT  sleeping %s before batch %d", batchInterval, batchNum+1)
			time.Sleep(batchInterval)
		}
	}

	copyElapsed := time.Since(copyStart)
	overallRate := filesPerSec(totalCopied.Load(), copyElapsed)
	expectedPuts := int64(len(keys) * len(dests))

	fmt.Println("\n--- copy summary ---")
	fmt.Printf("objects:     %d\n", len(keys))
	fmt.Printf("dests:       %d\n", len(dests))
	fmt.Printf("puts:        %d\n", expectedPuts)
	fmt.Printf("batches:     %d\n", len(batches))
	fmt.Printf("copied:      %d\n", totalCopied.Load())
	fmt.Printf("failed:      %d\n", totalFailed.Load())
	fmt.Printf("bytes:       %d\n", totalBytes.Load())
	fmt.Printf("elapsed:     %s\n", copyElapsed)
	fmt.Printf("rate:        %.2f files/s\n", overallRate)

	log.Printf("COPY SUMMARY objects=%d dests=%d puts=%d copied=%d failed=%d bytes=%d batches=%d elapsed=%s rate=%.2f files/s",
		len(keys), len(dests), expectedPuts, totalCopied.Load(), totalFailed.Load(), totalBytes.Load(),
		len(batches), copyElapsed, overallRate)
}

type destTarget struct {
	bucket string
	region string
	prefix string
	client *s3.Client
}

type batchStats struct {
	copied int64
	failed int64
	bytes  int64
}

func runBatch(ctx context.Context, sourceClient *s3.Client, dests []destTarget, workers int,
	sourceBucket string, keys []string, retryDelay time.Duration) (copied, failed, bytes int64) {

	jobs := make(chan string, len(keys))
	var stats batchStats

	var wg sync.WaitGroup
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for key := range jobs {
				for _, dest := range dests {
					destKey := dest.prefix + key
					n, err := copyObjectUntilSuccess(ctx, sourceClient, dest.client,
						sourceBucket, dest.bucket, key, destKey, retryDelay)
					if err != nil {
						atomic.AddInt64(&stats.failed, 1)
						log.Printf("COPY STOP s3://%s/%s -> s3://%s/%s | %v",
							sourceBucket, key, dest.bucket, destKey, err)
						continue
					}
					atomic.AddInt64(&stats.copied, 1)
					atomic.AddInt64(&stats.bytes, n)
				}
			}
		}()
	}

	for _, key := range keys {
		jobs <- key
	}
	close(jobs)
	wg.Wait()

	return stats.copied, stats.failed, stats.bytes
}

func copyObjectUntilSuccess(ctx context.Context, sourceClient, destClient *s3.Client,
	srcBucket, dstBucket, srcKey, dstKey string, retryDelay time.Duration) (int64, error) {

	attempt := 0
	for {
		if err := ctx.Err(); err != nil {
			return 0, err
		}

		attempt++
		n, status, err := transferObject(ctx, sourceClient, destClient, srcBucket, dstBucket, srcKey, dstKey)
		if err == nil {
			if attempt > 1 {
				log.Printf("COPY OK   s3://%s/%s -> s3://%s/%s | http_status=%d bytes=%d (succeeded on attempt %d)",
					srcBucket, srcKey, dstBucket, dstKey, status, n, attempt)
			} else {
				log.Printf("COPY OK   s3://%s/%s -> s3://%s/%s | http_status=%d bytes=%d",
					srcBucket, srcKey, dstBucket, dstKey, status, n)
			}
			return n, nil
		}

		log.Printf("COPY FAIL s3://%s/%s -> s3://%s/%s | attempt=%d | %s | retrying in %s",
			srcBucket, srcKey, dstBucket, dstKey, attempt, formatS3Err(status, err), retryDelay)

		if !sleepWithContext(ctx, retryDelay) {
			return 0, ctx.Err()
		}
	}
}

func parseCSV(v string) []string {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func formatDests(dests []destTarget) string {
	parts := make([]string, 0, len(dests))
	for _, d := range dests {
		parts = append(parts, fmt.Sprintf("s3://%s (%s)", d.bucket, d.region))
	}
	return strings.Join(parts, ", ")
}

func listKeysWithRetry(ctx context.Context, client *s3.Client, bucket, prefix string, retryDelay time.Duration) ([]string, error) {
	attempt := 0
	for {
		if err := ctx.Err(); err != nil {
			return nil, err
		}

		attempt++
		keys, err := listKeys(ctx, client, bucket, prefix)
		if err == nil {
			if attempt > 1 {
				log.Printf("LIST OK objects=%d (succeeded on attempt %d)", len(keys), attempt)
			}
			return keys, nil
		}

		log.Printf("LIST FAIL attempt=%d | %s | retrying in %s",
			attempt, formatS3Err(statusFromErr(err), err), retryDelay)

		if !sleepWithContext(ctx, retryDelay) {
			return nil, ctx.Err()
		}
	}
}

func sleepWithContext(ctx context.Context, d time.Duration) bool {
	timer := time.NewTimer(d)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}

func chunkKeys(keys []string, size int) [][]string {
	if size <= 0 || size >= len(keys) {
		return [][]string{keys}
	}
	batches := make([][]string, 0, (len(keys)+size-1)/size)
	for i := 0; i < len(keys); i += size {
		end := i + size
		if end > len(keys) {
			end = len(keys)
		}
		batches = append(batches, keys[i:end])
	}
	return batches
}

func filesPerSec(count int64, elapsed time.Duration) float64 {
	if elapsed <= 0 || count == 0 {
		return 0
	}
	return float64(count) / elapsed.Seconds()
}

func newS3Client(ctx context.Context, region string) (*s3.Client, error) {
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		return nil, err
	}
	return s3.NewFromConfig(cfg), nil
}

func listKeys(ctx context.Context, client *s3.Client, bucket, prefix string) ([]string, error) {
	var keys []string

	paginator := s3.NewListObjectsV2Paginator(client, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
		Prefix: aws.String(prefix),
	})

	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, err
		}
		for _, obj := range page.Contents {
			if obj.Key != nil {
				keys = append(keys, *obj.Key)
			}
		}
	}

	return keys, nil
}

func transferObject(ctx context.Context, sourceClient, destClient *s3.Client, srcBucket, dstBucket, srcKey, dstKey string) (int64, int, error) {
	getOut, err := sourceClient.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(srcBucket),
		Key:    aws.String(srcKey),
	})
	if err != nil {
		return 0, statusFromErr(err), fmt.Errorf("GetObject: %w", err)
	}
	defer getOut.Body.Close()

	putIn := &s3.PutObjectInput{
		Bucket: aws.String(dstBucket),
		Key:    aws.String(dstKey),
	}
	if getOut.ContentType != nil {
		putIn.ContentType = getOut.ContentType
	}
	if getOut.ContentEncoding != nil {
		putIn.ContentEncoding = getOut.ContentEncoding
	}
	if getOut.Metadata != nil {
		putIn.Metadata = getOut.Metadata
	}

	var size int64
	if getOut.ContentLength != nil {
		size = *getOut.ContentLength
		putIn.ContentLength = getOut.ContentLength
		putIn.Body = getOut.Body
	} else {
		data, err := io.ReadAll(getOut.Body)
		if err != nil {
			return 0, statusFromErr(err), fmt.Errorf("read object body: %w", err)
		}
		size = int64(len(data))
		putIn.ContentLength = aws.Int64(size)
		putIn.Body = bytes.NewReader(data)
	}

	_, err = destClient.PutObject(ctx, putIn)
	if err != nil {
		return 0, statusFromErr(err), fmt.Errorf("PutObject: %w", err)
	}

	return size, 200, nil
}

func statusFromErr(err error) int {
	var respErr *smithyhttp.ResponseError
	if errors.As(err, &respErr) {
		return respErr.HTTPStatusCode()
	}
	return 0
}

func formatS3Err(status int, err error) string {
	var parts []string
	if status > 0 {
		parts = append(parts, fmt.Sprintf("http_status=%d", status))
	}

	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		parts = append(parts,
			fmt.Sprintf("error_code=%s", apiErr.ErrorCode()),
			fmt.Sprintf("error_message=%q", apiErr.ErrorMessage()),
		)
	}

	parts = append(parts, fmt.Sprintf("raw_error=%v", err))
	return strings.Join(parts, " ")
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func envDuration(key string, fallback time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return fallback
	}
	return d
}

func loadEnvFile(name string) {
	path := name
	if _, err := os.Stat(path); os.IsNotExist(err) {
		path = filepath.Join(filepath.Dir(os.Args[0]), name)
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return
		}
	}

	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		key, val, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		val = strings.TrimSpace(val)
		val = strings.Trim(val, `"'`)
		if val == "" {
			continue
		}
		if os.Getenv(key) == "" {
			os.Setenv(key, val)
		}
	}
}
