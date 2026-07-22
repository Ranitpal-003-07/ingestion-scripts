# sqs_poll

Poll an SQS queue and receive messages using the EC2 instance IAM role.

## Config

```bash
cp .env.example .env
```

Required in `.env`:

```bash
AWS_REGION=ap-south-1
SQS_QUEUE_URL=https://sqs.ap-south-1.amazonaws.com/123456789012/your-queue-name
```

Optional:

| Variable | Default | Description |
|----------|---------|-------------|
| `SQS_MAX_MESSAGES` | `1` | Messages per poll (1–10) |
| `SQS_WAIT_SECONDS` | `20` | Long poll wait (0–20 seconds) |
| `SQS_POLL_ROUNDS` | `1` | Number of poll rounds |
| `SQS_POLL_INTERVAL` | off | Wait between rounds (e.g. `5s`) |
| `SQS_DELETE_ON_RECEIVE` | `false` | Delete message after receiving |

## Run

```bash
cd sqs_poll
go mod tidy
go run .
```

## IAM permissions

The instance role needs:

```json
{
  "Effect": "Allow",
  "Action": ["sqs:ReceiveMessage", "sqs:GetQueueAttributes"],
  "Resource": "arn:aws:sqs:REGION:ACCOUNT_ID:QUEUE_NAME"
}
```

Add `sqs:DeleteMessage` only if `SQS_DELETE_ON_RECEIVE=true`.

## Output

Prints each message body, ID, receipt handle, and attributes. On failure, logs HTTP status, error code, and message:

```
ReceiveMessage failed | http_status=403 error_code=AccessDenied error_message="..." raw_error=...
```
