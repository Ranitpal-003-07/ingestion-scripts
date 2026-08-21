package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"math/rand"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/smithy-go"
)

const (
	defaultBucket = "test-logs-aws-bucket"
	defaultRegion = "ap-south-1"
	// Used only when the bucket/prefix is empty, to verify GetObject is allowed.
	probeKey = "__test_s3_permission_probe__/does-not-exist"
)

func main() {
	loadKeyFile("key.txt")

	bucket := envOr("S3_BUCKET", defaultBucket)
	prefix := os.Getenv("S3_PREFIX")
	region := envOr("AWS_REGION", defaultRegion)

	ctx := context.Background()

	// Uses default credential chain: IAM role (EC2/ECS/Lambda), ~/.aws/credentials,
	// AWS SSO, or env vars — no access keys required when running with an IAM role.
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		log.Fatalf("load AWS config: %v", err)
	}

	client := s3.NewFromConfig(cfg)

	// --- Call 1: ListObjectsV2 ---
	log.Printf("Listing objects in s3://%s (prefix=%q, region=%s)", bucket, prefix, region)
	listStart := time.Now()

	keys, err := listKeys(ctx, client, bucket, prefix)
	if err != nil {
		log.Fatalf("list objects (need s3:ListBucket): %v", err)
	}

	listElapsed := time.Since(listStart)
	log.Printf("List OK: %d objects in %s (s3:ListBucket allowed)", len(keys), listElapsed)

	fmt.Println("\n--- list check ---")
	fmt.Printf("bucket:  %s\n", bucket)
	fmt.Printf("region:  %s\n", region)
	fmt.Printf("prefix:  %q\n", prefix)
	fmt.Printf("result:  ListObjectsV2 succeeded\n")
	fmt.Printf("objects: %d\n", len(keys))

	// --- Call 2: GetObject ---
	if len(keys) == 0 {
		checkGetWhenEmpty(ctx, client, bucket)
		return
	}

	rng := rand.New(rand.NewSource(time.Now().UnixNano()))
	key := keys[rng.Intn(len(keys))]
	getRandomObject(ctx, client, bucket, key, len(keys), listElapsed)
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

// checkGetWhenEmpty verifies Get permission when there is nothing to download.
// GetObject on a missing key returns NoSuchKey if s3:GetObject is allowed,
// or AccessDenied if it is not.
func checkGetWhenEmpty(ctx context.Context, client *s3.Client, bucket string) {
	log.Printf("Bucket/prefix is empty — probing Get permission with missing key %q", probeKey)
	getStart := time.Now()

	_, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(probeKey),
	})
	getElapsed := time.Since(getStart)

	fmt.Println("\n--- get check (empty bucket) ---")
	fmt.Printf("probe key: s3://%s/%s\n", bucket, probeKey)
	fmt.Printf("elapsed:   %s\n", getElapsed)

	switch {
	case err == nil:
		// Extremely unlikely: probe key somehow exists.
		fmt.Println("result:    GetObject succeeded (unexpected — probe key existed)")
		fmt.Println("permission:s3:GetObject allowed")
		return

	case isAPIErrorCode(err, "NoSuchKey") || isNotFound(err):
		fmt.Println("result:    GetObject returned NoSuchKey (object missing, as expected)")
		fmt.Println("permission:s3:GetObject allowed")
		fmt.Println("note:      nothing to download; random get skipped because bucket/prefix is empty")
		return

	case isAPIErrorCode(err, "AccessDenied") || isAPIErrorCode(err, "AllAccessDisabled"):
		log.Fatalf("get permission check failed: AccessDenied — have ListBucket but not GetObject: %v", err)

	default:
		log.Fatalf("get permission check failed: %v", err)
	}
}

func getRandomObject(ctx context.Context, client *s3.Client, bucket, key string, listed int, listElapsed time.Duration) {
	log.Printf("Getting random object: s3://%s/%s", bucket, key)
	getStart := time.Now()

	out, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		if isAPIErrorCode(err, "AccessDenied") {
			log.Fatalf("get object (need s3:GetObject): AccessDenied: %v", err)
		}
		log.Fatalf("get object: %v", err)
	}
	defer out.Body.Close()

	n, err := io.Copy(io.Discard, out.Body)
	if err != nil {
		log.Fatalf("read object body: %v", err)
	}

	getElapsed := time.Since(getStart)
	log.Printf("Get OK: %d bytes in %s (s3:GetObject allowed, Content-Type: %s)",
		n, getElapsed, aws.ToString(out.ContentType))

	fmt.Println("\n--- get check ---")
	fmt.Printf("got:         s3://%s/%s\n", bucket, key)
	fmt.Printf("bytes read:  %d (%s)\n", n, getElapsed)
	fmt.Printf("permission:  s3:GetObject allowed\n")

	fmt.Println("\n--- summary ---")
	fmt.Printf("bucket:      %s\n", bucket)
	fmt.Printf("listed:      %d objects (%s)\n", listed, listElapsed)
	fmt.Printf("got:         s3://%s/%s\n", bucket, key)
	fmt.Printf("bytes read:  %d (%s)\n", n, getElapsed)
}

func isNotFound(err error) bool {
	var nf *types.NotFound
	var nsk *types.NoSuchKey
	return errors.As(err, &nf) || errors.As(err, &nsk)
}

func isAPIErrorCode(err error, code string) bool {
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		return apiErr.ErrorCode() == code
	}
	return false
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// loadKeyFile reads export VAR=value lines from key.txt (non-secret config only).
func loadKeyFile(name string) {
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
		if val == "" {
			continue
		}
		if os.Getenv(key) == "" {
			os.Setenv(key, val)
		}
	}
}
