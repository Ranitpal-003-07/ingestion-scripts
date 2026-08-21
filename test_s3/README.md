# test_s3

Small Go script that hits an S3 bucket with two API calls:

1. **ListObjectsV2** — list all object keys (optionally filtered by prefix)
2. **GetObject** — if the bucket has objects, download one random key; if empty, still check Get permission by getting a missing probe key (`NoSuchKey` = Get allowed, `AccessDenied` = List only)

## Run with default IAM (no access keys)

The script uses the AWS SDK **default credential chain**. You do **not** need to set `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` if any of these apply:

| Source | Setup |
|--------|-------|
| EC2 / ECS / Lambda | Attach an IAM role to the instance/task |
| Local dev | Run `aws configure` once (writes `~/.aws/credentials`) |
| SSO | Run `aws sso login --profile your-profile` and set `AWS_PROFILE` |

Bucket and region default from `key.txt` (or override via env):

```bash
cd test_s3
go run .
```

That's it — no keys exported.

### IAM permissions needed

Attach one of these to the IAM role/user:

**Option A — AWS managed policy (simplest):**

```
AmazonS3ReadOnlyAccess
```

Covers `s3:ListBucket` and `s3:GetObject` on all buckets.

**Option B — Scoped to one bucket:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::test-logs-aws-bucket"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::test-logs-aws-bucket/*"
    }
  ]
}
```

| Permission | Used by |
|------------|---------|
| `s3:ListBucket` | List call |
| `s3:GetObject` | Random get call |

No write permissions needed.

## Optional overrides

```bash
export S3_BUCKET=other-bucket
export AWS_REGION=us-east-1
export S3_PREFIX=logs/2026/     # limit list + random pick
export AWS_PROFILE=my-sso-profile
go run .
```

Values in env vars take precedence over `key.txt`.
