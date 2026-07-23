# Queue_permision_test

Probe an SQS queue using the EC2 instance IAM role and report **all standard SQS permissions**.

## Config

```bash
cp .env.example .env
```

```bash
SQS_QUEUE_URL=https://sqs.REGION.amazonaws.com/ACCOUNT_ID/QUEUE_NAME
# Optional: SQS_TEST_PURGE=true   # WARNING: deletes ALL messages in queue
```

## Run

```bash
cd Queue_permision_test
go mod tidy
go run .
```

## Permissions tested

### Queue metadata & config
| IAM permission | API |
|----------------|-----|
| `sqs:GetQueueAttributes` | GetQueueAttributes |
| `sqs:GetQueueUrl` | GetQueueUrl |
| `sqs:ListQueues` | ListQueues |
| `sqs:ListQueueTags` | ListQueueTags |
| `sqs:TagQueue` | TagQueue (adds probe tag, then removes) |
| `sqs:UntagQueue` | UntagQueue |
| `sqs:SetQueueAttributes` | SetQueueAttributes (no-op: resets VisibilityTimeout to current value) |

### Messages
| IAM permission | API |
|----------------|-----|
| `sqs:ReceiveMessage` | ReceiveMessage |
| `sqs:SendMessage` | SendMessage |
| `sqs:SendMessageBatch` | SendMessageBatch |
| `sqs:ChangeMessageVisibility` | ChangeMessageVisibility (30s timeout) |
| `sqs:ChangeMessageVisibilityBatch` | ChangeMessageVisibilityBatch |
| `sqs:DeleteMessage` | DeleteMessage |
| `sqs:DeleteMessageBatch` | DeleteMessageBatch |

### DLQ / message move
| IAM permission | API |
|----------------|-----|
| `sqs:ListMessageMoveTasks` | ListMessageMoveTasks |
| `sqs:StartMessageMoveTask` | skipped (needs DLQ setup) |
| `sqs:CancelMessageMoveTask` | skipped (needs active task) |

### Skipped (destructive / unsafe)
| IAM permission | Why skipped |
|----------------|-------------|
| `sqs:PurgeQueue` | Set `SQS_TEST_PURGE=true` to test — **deletes all messages** |
| `sqs:DeleteQueue` | Would delete the queue |
| `sqs:CreateQueue` | Would create a new queue |
| `sqs:AddPermission` | Legacy queue policy API |
| `sqs:RemovePermission` | Legacy queue policy API |

Probe messages use body prefix `__queue_permission_probe__` and are cleaned up after delete tests.

## Output

```
ALLOW  sqs:ChangeMessageVisibility    ChangeMessageVisibility | visibility_timeout=30s
DENY   sqs:SendMessage                 SendMessage | http_status=403 error_code=AccessDenied ...

--- allowed ---
  + sqs:GetQueueAttributes
  + sqs:ReceiveMessage

--- denied ---
  - sqs:SendMessage (AccessDenied)
```

Exit code **1** if any non-skipped check is denied.
