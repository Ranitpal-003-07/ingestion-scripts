package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"log"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/aws/smithy-go"
	smithyhttp "github.com/aws/smithy-go/transport/http"
)

const (
	probeBody   = "__queue_permission_probe__"
	probeTagKey = "permission-probe"
)

func main() {
	loadEnvFile(".env")

	queueURL := os.Getenv("SQS_QUEUE_URL")
	if queueURL == "" {
		log.Fatal("SQS_QUEUE_URL is required (set in .env or env)")
	}

	region := envOr("AWS_REGION", "")
	if region == "" {
		var err error
		region, err = regionFromQueueURL(queueURL)
		if err != nil {
			log.Fatalf("parse queue URL region: %v (set AWS_REGION in .env)", err)
		}
	}

	testPurge := envBool("SQS_TEST_PURGE", false)

	ctx := context.Background()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		log.Fatalf("load AWS config: %v", err)
	}

	client := sqs.NewFromConfig(cfg)
	queueName, err := queueNameFromURL(queueURL)
	if err != nil {
		log.Fatalf("parse queue name: %v", err)
	}

	log.Printf("checking SQS permissions (region=%s)", region)
	log.Printf("queue_url:  %s", queueURL)
	log.Printf("queue_name: %s", queueName)
	fmt.Println()

	var results []result

	// --- Queue read / list ---
	results = append(results, runCheck(check{
		permission: "sqs:GetQueueAttributes",
		api:        "GetQueueAttributes",
		run: func() (string, error) {
			out, err := client.GetQueueAttributes(ctx, &sqs.GetQueueAttributesInput{
				QueueUrl:       aws.String(queueURL),
				AttributeNames: []types.QueueAttributeName{types.QueueAttributeNameAll},
			})
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("%d attributes", len(out.Attributes)), nil
		},
	}))

	results = append(results, runCheck(check{
		permission: "sqs:GetQueueUrl",
		api:        "GetQueueUrl",
		run: func() (string, error) {
			out, err := client.GetQueueUrl(ctx, &sqs.GetQueueUrlInput{
				QueueName: aws.String(queueName),
			})
			if err != nil {
				return "", err
			}
			return aws.ToString(out.QueueUrl), nil
		},
	}))

	results = append(results, runCheck(check{
		permission: "sqs:ListQueues",
		api:        "ListQueues",
		run: func() (string, error) {
			out, err := client.ListQueues(ctx, &sqs.ListQueuesInput{
				QueueNamePrefix: aws.String(queueName),
				MaxResults:      aws.Int32(10),
			})
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("matched %d queue(s)", len(out.QueueUrls)), nil
		},
	}))

	results = append(results, runCheck(check{
		permission: "sqs:ListQueueTags",
		api:        "ListQueueTags",
		run: func() (string, error) {
			out, err := client.ListQueueTags(ctx, &sqs.ListQueueTagsInput{
				QueueUrl: aws.String(queueURL),
			})
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("%d tag(s)", len(out.Tags)), nil
		},
	}))

	// --- Queue tags ---
	tagValue := time.Now().UTC().Format(time.RFC3339)
	results = append(results, runCheck(check{
		permission: "sqs:TagQueue",
		api:        "TagQueue",
		run: func() (string, error) {
			_, err := client.TagQueue(ctx, &sqs.TagQueueInput{
				QueueUrl: aws.String(queueURL),
				Tags:     map[string]string{probeTagKey: tagValue},
			})
			return "tag set", err
		},
	}))

	if findAllowed(results, "sqs:TagQueue") {
		results = append(results, runCheck(check{
			permission: "sqs:UntagQueue",
			api:        "UntagQueue",
			run: func() (string, error) {
				_, err := client.UntagQueue(ctx, &sqs.UntagQueueInput{
					QueueUrl: aws.String(queueURL),
					TagKeys:  []string{probeTagKey},
				})
				return "tag removed", err
			},
		}))
	} else {
		results = append(results, skipped("sqs:UntagQueue", "UntagQueue", "TagQueue not allowed"))
	}

	// --- SetQueueAttributes (set VisibilityTimeout to current value) ---
	results = append(results, runCheck(check{
		permission: "sqs:SetQueueAttributes",
		api:        "SetQueueAttributes",
		run: func() (string, error) {
			attrs, err := client.GetQueueAttributes(ctx, &sqs.GetQueueAttributesInput{
				QueueUrl: aws.String(queueURL),
				AttributeNames: []types.QueueAttributeName{
					types.QueueAttributeNameVisibilityTimeout,
				},
			})
			if err != nil {
				return "", fmt.Errorf("read current timeout: %w", err)
			}
			timeout := attrs.Attributes[string(types.QueueAttributeNameVisibilityTimeout)]
			_, err = client.SetQueueAttributes(ctx, &sqs.SetQueueAttributesInput{
				QueueUrl: aws.String(queueURL),
				Attributes: map[string]string{
					string(types.QueueAttributeNameVisibilityTimeout): timeout,
				},
			})
			return "visibility_timeout=" + timeout + " (no-op update)", err
		},
	}))

	// --- Receive (empty poll) ---
	results = append(results, runCheck(check{
		permission: "sqs:ReceiveMessage",
		api:        "ReceiveMessage",
		run: func() (string, error) {
			out, err := client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
				QueueUrl:            aws.String(queueURL),
				MaxNumberOfMessages: 1,
				WaitTimeSeconds:     0,
			})
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("received %d message(s)", len(out.Messages)), nil
		},
	}))

	// --- Send ---
	stamp := time.Now().UTC().Format(time.RFC3339Nano)
	results = append(results, runCheck(check{
		permission: "sqs:SendMessage",
		api:        "SendMessage",
		run: func() (string, error) {
			out, err := client.SendMessage(ctx, &sqs.SendMessageInput{
				QueueUrl:    aws.String(queueURL),
				MessageBody: aws.String(probeBody + "-single-" + stamp),
			})
			if err != nil {
				return "", err
			}
			return "message_id=" + aws.ToString(out.MessageId), nil
		},
	}))

	results = append(results, runCheck(check{
		permission: "sqs:SendMessageBatch",
		api:        "SendMessageBatch",
		run: func() (string, error) {
			out, err := client.SendMessageBatch(ctx, &sqs.SendMessageBatchInput{
				QueueUrl: aws.String(queueURL),
				Entries: []types.SendMessageBatchRequestEntry{
					{
						Id:          aws.String("probe-1"),
						MessageBody: aws.String(probeBody + "-batch-1-" + stamp),
					},
					{
						Id:          aws.String("probe-2"),
						MessageBody: aws.String(probeBody + "-batch-2-" + stamp),
					},
				},
			})
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("successful=%d failed=%d",
				len(out.Successful), len(out.Failed)), nil
		},
	}))

	// --- Message-level ops (visibility, delete, batch) ---
	if findAllowed(results, "sqs:ReceiveMessage") &&
		(findAllowed(results, "sqs:SendMessage") || findAllowed(results, "sqs:SendMessageBatch")) {
		results = append(results, probeMessageOps(ctx, client, queueURL)...)
	} else {
		results = append(results,
			skipped("sqs:ChangeMessageVisibility", "ChangeMessageVisibility", "need Send + Receive"),
			skipped("sqs:ChangeMessageVisibilityBatch", "ChangeMessageVisibilityBatch", "need Send + Receive"),
			skipped("sqs:DeleteMessage", "DeleteMessage", "need Send + Receive"),
			skipped("sqs:DeleteMessageBatch", "DeleteMessageBatch", "need Send + Receive"),
		)
	}

	// --- Message move tasks (DLQ redrive APIs) ---
	results = append(results, runCheck(check{
		permission: "sqs:ListMessageMoveTasks",
		api:        "ListMessageMoveTasks",
		run: func() (string, error) {
			out, err := client.ListMessageMoveTasks(ctx, &sqs.ListMessageMoveTasksInput{
				SourceArn: aws.String(queueURLToArn(queueURL, region)),
			})
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("%d task(s)", len(out.Results)), nil
		},
	}))

	results = append(results, skipped("sqs:StartMessageMoveTask", "StartMessageMoveTask",
		"not run (requires DLQ redrive setup)"))
	results = append(results, skipped("sqs:CancelMessageMoveTask", "CancelMessageMoveTask",
		"not run (requires active move task)"))

	// --- Destructive / not safe to auto-test ---
	if testPurge {
		results = append(results, runCheck(check{
			permission: "sqs:PurgeQueue",
			api:        "PurgeQueue",
			run: func() (string, error) {
				_, err := client.PurgeQueue(ctx, &sqs.PurgeQueueInput{
					QueueUrl: aws.String(queueURL),
				})
				return "purge initiated (deletes ALL messages)", err
			},
		}))
	} else {
		results = append(results, skipped("sqs:PurgeQueue", "PurgeQueue",
			"set SQS_TEST_PURGE=true to test (deletes all messages)"))
	}

	results = append(results, skipped("sqs:DeleteQueue", "DeleteQueue",
		"not run (would delete the queue)"))
	results = append(results, skipped("sqs:CreateQueue", "CreateQueue",
		"not run (creates a new queue)"))
	results = append(results, skipped("sqs:AddPermission", "AddPermission",
		"not run (legacy queue policy API)"))
	results = append(results, skipped("sqs:RemovePermission", "RemovePermission",
		"not run (legacy queue policy API)"))

	printSummary(results)

	denied := 0
	for _, r := range results {
		if !r.allowed && !strings.HasPrefix(r.detail, "skipped") && !strings.HasPrefix(r.detail, "not run") {
			denied++
		}
	}
	if denied > 0 {
		os.Exit(1)
	}
}

func probeMessageOps(ctx context.Context, client *sqs.Client, queueURL string) []result {
	var out []result

	recv, err := client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
		QueueUrl:            aws.String(queueURL),
		MaxNumberOfMessages: 10,
		WaitTimeSeconds:     2,
	})
	if err != nil {
		out = append(out, runCheck(check{
			permission: "sqs:ReceiveMessage",
			api:        "ReceiveMessage (probe fetch)",
			run:        func() (string, error) { return "", err },
		}))
		return append(out,
			skipped("sqs:ChangeMessageVisibility", "ChangeMessageVisibility", "probe receive failed"),
			skipped("sqs:ChangeMessageVisibilityBatch", "ChangeMessageVisibilityBatch", "probe receive failed"),
			skipped("sqs:DeleteMessage", "DeleteMessage", "probe receive failed"),
			skipped("sqs:DeleteMessageBatch", "DeleteMessageBatch", "probe receive failed"),
		)
	}

	// Only probe messages sent by this script.
	var probe []types.Message
	for _, m := range recv.Messages {
		if strings.Contains(aws.ToString(m.Body), probeBody) {
			probe = append(probe, m)
		}
	}
	if len(probe) == 0 {
		return []result{
			skipped("sqs:ChangeMessageVisibility", "ChangeMessageVisibility", "no probe messages in queue"),
			skipped("sqs:ChangeMessageVisibilityBatch", "ChangeMessageVisibilityBatch", "no probe messages"),
			skipped("sqs:DeleteMessage", "DeleteMessage", "no probe messages"),
			skipped("sqs:DeleteMessageBatch", "DeleteMessageBatch", "no probe messages"),
		}
	}

	r0 := aws.ToString(probe[0].ReceiptHandle)

	out = append(out, runCheck(check{
		permission: "sqs:ChangeMessageVisibility",
		api:        "ChangeMessageVisibility",
		run: func() (string, error) {
			_, err := client.ChangeMessageVisibility(ctx, &sqs.ChangeMessageVisibilityInput{
				QueueUrl:          aws.String(queueURL),
				ReceiptHandle:     aws.String(r0),
				VisibilityTimeout: 30,
			})
			return "visibility_timeout=30s", err
		},
	}))

	if len(probe) >= 2 {
		entries := make([]types.ChangeMessageVisibilityBatchRequestEntry, 0, len(probe))
		for i, m := range probe {
			entries = append(entries, types.ChangeMessageVisibilityBatchRequestEntry{
				Id:                aws.String(fmt.Sprintf("vis-%d", i)),
				ReceiptHandle:     m.ReceiptHandle,
				VisibilityTimeout: 30,
			})
		}
		out = append(out, runCheck(check{
			permission: "sqs:ChangeMessageVisibilityBatch",
			api:        "ChangeMessageVisibilityBatch",
			run: func() (string, error) {
				res, err := client.ChangeMessageVisibilityBatch(ctx, &sqs.ChangeMessageVisibilityBatchInput{
					QueueUrl: aws.String(queueURL),
					Entries:  entries,
				})
				if err != nil {
					return "", err
				}
				return fmt.Sprintf("successful=%d failed=%d",
					len(res.Successful), len(res.Failed)), nil
			},
		}))
	} else {
		out = append(out, skipped("sqs:ChangeMessageVisibilityBatch", "ChangeMessageVisibilityBatch",
			"need 2+ probe messages"))
	}

	out = append(out, runCheck(check{
		permission: "sqs:DeleteMessage",
		api:        "DeleteMessage",
		run: func() (string, error) {
			_, err := client.DeleteMessage(ctx, &sqs.DeleteMessageInput{
				QueueUrl:      aws.String(queueURL),
				ReceiptHandle: aws.String(r0),
			})
			return "deleted 1 probe message", err
		},
	}))

	remaining := probe[1:]
	if len(remaining) > 0 {
		entries := make([]types.DeleteMessageBatchRequestEntry, 0, len(remaining))
		for i, m := range remaining {
			entries = append(entries, types.DeleteMessageBatchRequestEntry{
				Id:            aws.String(fmt.Sprintf("del-%d", i)),
				ReceiptHandle: m.ReceiptHandle,
			})
		}
		out = append(out, runCheck(check{
			permission: "sqs:DeleteMessageBatch",
			api:        "DeleteMessageBatch",
			run: func() (string, error) {
				res, err := client.DeleteMessageBatch(ctx, &sqs.DeleteMessageBatchInput{
					QueueUrl: aws.String(queueURL),
					Entries:  entries,
				})
				if err != nil {
					return "", err
				}
				return fmt.Sprintf("successful=%d failed=%d",
					len(res.Successful), len(res.Failed)), nil
			},
		}))
	} else {
		out = append(out, skipped("sqs:DeleteMessageBatch", "DeleteMessageBatch",
			"only 1 probe message available"))
	}

	return out
}

func queueURLToArn(queueURL, region string) string {
	// https://sqs.region.amazonaws.com/account-id/queue-name
	u, err := url.Parse(queueURL)
	if err != nil {
		return queueURL
	}
	parts := strings.Split(strings.TrimPrefix(u.Path, "/"), "/")
	if len(parts) >= 2 {
		return fmt.Sprintf("arn:aws:sqs:%s:%s:%s", region, parts[0], parts[1])
	}
	return queueURL
}

func skipped(perm, api, reason string) result {
	log.Printf("SKIP   %-28s %s | %s", perm, api, reason)
	return result{
		permission: perm,
		api:        api,
		allowed:    false,
		detail:     "skipped (" + reason + ")",
	}
}

type check struct {
	permission string
	api        string
	run        func() (detail string, err error)
}

type result struct {
	permission string
	api        string
	allowed    bool
	httpStatus int
	errorCode  string
	errorMsg   string
	detail     string
}

func runCheck(c check) result {
	detail, err := c.run()
	if err == nil {
		log.Printf("ALLOW  %-28s %s | %s", c.permission, c.api, detail)
		return result{
			permission: c.permission,
			api:        c.api,
			allowed:    true,
			httpStatus: 200,
			detail:     detail,
		}
	}

	status, code, msg := parseErr(err)
	log.Printf("DENY   %-28s %s | http_status=%d error_code=%s error_message=%q",
		c.permission, c.api, status, code, msg)
	return result{
		permission: c.permission,
		api:        c.api,
		allowed:    false,
		httpStatus: status,
		errorCode:  code,
		errorMsg:   msg,
		detail:     err.Error(),
	}
}

func printSummary(results []result) {
	fmt.Println("\n--- permission summary ---")
	fmt.Printf("%-32s %-30s %-7s %-6s %s\n", "IAM_PERMISSION", "API", "ALLOWED", "HTTP", "DETAIL")
	fmt.Println(strings.Repeat("-", 120))
	for _, r := range results {
		allowed := "no"
		if r.allowed {
			allowed = "yes"
		}
		status := "-"
		if r.httpStatus > 0 {
			status = fmt.Sprintf("%d", r.httpStatus)
		}
		detail := r.detail
		if !r.allowed && r.errorCode != "" {
			detail = fmt.Sprintf("error_code=%s error_message=%q", r.errorCode, r.errorMsg)
		}
		fmt.Printf("%-32s %-30s %-7s %-6s %s\n", r.permission, r.api, allowed, status, detail)
	}

	fmt.Println("\n--- allowed ---")
	printPermList(results, true)
	fmt.Println("\n--- denied ---")
	printPermList(results, false)
	fmt.Println("\n--- skipped / not run ---")
	for _, r := range results {
		if strings.HasPrefix(r.detail, "skipped") || strings.HasPrefix(r.detail, "not run") {
			fmt.Printf("  ~ %s (%s)\n", r.permission, r.detail)
		}
	}
}

func printPermList(results []result, allowed bool) {
	any := false
	for _, r := range results {
		if r.allowed == allowed && !strings.HasPrefix(r.detail, "skipped") && !strings.HasPrefix(r.detail, "not run") {
			any = true
			suffix := ""
			if !allowed && r.errorCode != "" {
				suffix = " (" + r.errorCode + ")"
			}
			fmt.Printf("  %s%s\n", r.permission, suffix)
		}
	}
	if !any {
		fmt.Println("  (none)")
	}
}

func findAllowed(results []result, perm string) bool {
	for _, r := range results {
		if r.permission == perm && r.allowed {
			return true
		}
	}
	return false
}

func parseErr(err error) (status int, code, msg string) {
	var respErr *smithyhttp.ResponseError
	if errors.As(err, &respErr) {
		status = respErr.HTTPStatusCode()
	}
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		code = apiErr.ErrorCode()
		msg = apiErr.ErrorMessage()
	}
	return status, code, msg
}

func regionFromQueueURL(queueURL string) (string, error) {
	u, err := url.Parse(queueURL)
	if err != nil {
		return "", err
	}
	parts := strings.Split(u.Hostname(), ".")
	if len(parts) >= 2 && parts[0] == "sqs" && parts[1] != "amazonaws" {
		return parts[1], nil
	}
	return "", fmt.Errorf("cannot detect region from URL host: %s", u.Hostname())
}

func queueNameFromURL(queueURL string) (string, error) {
	u, err := url.Parse(queueURL)
	if err != nil {
		return "", err
	}
	name := strings.TrimPrefix(u.Path, "/")
	if idx := strings.Index(name, "/"); idx >= 0 {
		name = name[idx+1:]
	}
	if name == "" {
		return "", fmt.Errorf("no queue name in URL")
	}
	return name, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envBool(key string, fallback bool) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(key)))
	if v == "" {
		return fallback
	}
	return v == "1" || v == "true" || v == "yes"
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
		val = strings.Trim(strings.TrimSpace(val), `"'`)
		if val == "" {
			continue
		}
		if os.Getenv(key) == "" {
			os.Setenv(key, val)
		}
	}
}
