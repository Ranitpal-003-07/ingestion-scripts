package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/aws/smithy-go"
	smithyhttp "github.com/aws/smithy-go/transport/http"
)

const defaultRegion = "ap-south-1"

func main() {
	loadEnvFile(".env")

	region := envOr("AWS_REGION", defaultRegion)
	queueURL := os.Getenv("SQS_QUEUE_URL")
	maxMessages := envInt("SQS_MAX_MESSAGES", 1)
	waitSeconds := envInt("SQS_WAIT_SECONDS", 20)
	pollRounds := envInt("SQS_POLL_ROUNDS", 1)
	pollInterval := envDuration("SQS_POLL_INTERVAL", 0)
	deleteOnReceive := envBool("SQS_DELETE_ON_RECEIVE", false)

	if queueURL == "" {
		log.Fatal("SQS_QUEUE_URL is required (set in .env or env)")
	}
	if maxMessages < 1 || maxMessages > 10 {
		log.Fatal("SQS_MAX_MESSAGES must be between 1 and 10")
	}
	if waitSeconds < 0 || waitSeconds > 20 {
		log.Fatal("SQS_WAIT_SECONDS must be between 0 and 20")
	}

	ctx := context.Background()

	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		log.Fatalf("load AWS config: %v", err)
	}

	client := sqs.NewFromConfig(cfg)

	log.Printf("polling queue (region=%s, wait=%ds, max_messages=%d, rounds=%d, delete=%t)",
		region, waitSeconds, maxMessages, pollRounds, deleteOnReceive)
	log.Printf("queue_url: %s", queueURL)

	round := 0
	for {
		round++
		if pollRounds > 0 && round > pollRounds {
			break
		}

		if pollRounds != 1 {
			log.Printf("--- poll round %d ---", round)
		}

		received, err := receiveMessages(ctx, client, queueURL, maxMessages, waitSeconds)
		if err != nil {
			fail("ReceiveMessage", err)
		}

		if len(received) == 0 {
			log.Println("no messages received")
		}

		for i, msg := range received {
			printMessage(i+1, msg)

			if deleteOnReceive && msg.ReceiptHandle != nil {
				if err := deleteMessage(ctx, client, queueURL, *msg.ReceiptHandle); err != nil {
					log.Printf("DELETE FAIL message_id=%s | %s",
						aws.ToString(msg.MessageId), formatSQSErr(statusFromErr(err), err))
				} else {
					log.Printf("DELETE OK message_id=%s", aws.ToString(msg.MessageId))
				}
			}
		}

		if pollRounds > 0 && round >= pollRounds {
			break
		}
		if pollInterval <= 0 {
			break
		}
		time.Sleep(pollInterval)
	}
}

func receiveMessages(ctx context.Context, client *sqs.Client, queueURL string, maxMessages, waitSeconds int) ([]types.Message, error) {
	out, err := client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
		QueueUrl:            aws.String(queueURL),
		MaxNumberOfMessages: int32(maxMessages),
		WaitTimeSeconds:     int32(waitSeconds),
		AttributeNames: []types.QueueAttributeName{
			types.QueueAttributeNameAll,
		},
		MessageAttributeNames: []string{"All"},
	})
	if err != nil {
		return nil, err
	}
	return out.Messages, nil
}

func deleteMessage(ctx context.Context, client *sqs.Client, queueURL, receiptHandle string) error {
	_, err := client.DeleteMessage(ctx, &sqs.DeleteMessageInput{
		QueueUrl:      aws.String(queueURL),
		ReceiptHandle: aws.String(receiptHandle),
	})
	return err
}

func printMessage(n int, msg types.Message) {
	fmt.Printf("\n--- message %d ---\n", n)
	fmt.Printf("http_status:    200\n")
	fmt.Printf("message_id:     %s\n", aws.ToString(msg.MessageId))
	fmt.Printf("receipt_handle: %s\n", aws.ToString(msg.ReceiptHandle))
	fmt.Printf("body:\n%s\n", aws.ToString(msg.Body))

	if len(msg.Attributes) > 0 {
		fmt.Println("attributes:")
		for k, v := range msg.Attributes {
			fmt.Printf("  %s: %s\n", k, v)
		}
	}

	if len(msg.MessageAttributes) > 0 {
		fmt.Println("message_attributes:")
		for k, v := range msg.MessageAttributes {
			fmt.Printf("  %s: ", k)
			switch {
			case v.StringValue != nil:
				fmt.Printf("%q (%s)\n", aws.ToString(v.StringValue), v.DataType)
			default:
				b, _ := json.Marshal(v)
				fmt.Println(string(b))
			}
		}
	}
}

func statusFromErr(err error) int {
	var respErr *smithyhttp.ResponseError
	if errors.As(err, &respErr) {
		return respErr.HTTPStatusCode()
	}
	return 0
}

func formatSQSErr(status int, err error) string {
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

func fail(op string, err error) {
	status := statusFromErr(err)
	log.Fatalf("%s failed | %s", op, formatSQSErr(status, err))
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

func envBool(key string, fallback bool) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(key)))
	if v == "" {
		return fallback
	}
	return v == "1" || v == "true" || v == "yes"
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
