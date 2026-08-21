# s3_copy

Copy all objects from one S3 bucket to another using the EC2 instance IAM role.
Uses **GetObject** on the source bucket and **PutObject** on the destination (data flows through the VM).

## Config

Copy the example and edit values:

```bash
cp .env.example .env
```

`.env` contents:

```bash
AWS_REGION=ap-south-1
S3_SOURCE_BUCKET=source-bucket
S3_DEST_BUCKET=dest-bucket
```

For **cross-region** copy, set each bucket's region:

```bash
S3_SOURCE_REGION=ap-south-1
S3_DEST_REGION=us-east-1
```

If `S3_SOURCE_REGION` / `S3_DEST_REGION` are omitted, both fall back to `AWS_REGION`.

Optional in `.env`:

```bash
S3_PREFIX=logs/2026/
S3_DEST_PREFIX=archive/
S3_COPY_WORKERS=10       # parallel transfers within each batch
S3_BATCH_SIZE=10         # files per batch before pausing
S3_BATCH_INTERVAL=5s     # wait between batches (e.g. 5s, 1m, 30s)
```

### Batch flow

1. Send up to `S3_BATCH_SIZE` files using `S3_COPY_WORKERS` in parallel
2. Log batch stats (sent, failed, bytes, elapsed, files/s)
3. Sleep for `S3_BATCH_INTERVAL`
4. Repeat until all files are copied

Set `S3_BATCH_INTERVAL=0` to run batches back-to-back with no pause.

Shell env vars override `.env`. Credentials come from the instance IAM role — no access keys in `.env`.

## Run

```bash
cd s3_copy
go mod tidy
go run .
```

## IAM permissions

The instance role needs:

| Action | Resource |
|--------|----------|
| `s3:ListBucket` | `arn:aws:s3:::SOURCE-BUCKET` |
| `s3:GetObject` | `arn:aws:s3:::SOURCE-BUCKET/*` |
| `s3:PutObject` | `arn:aws:s3:::DEST-BUCKET/*` |

Source and destination buckets may be in **different regions** — set `S3_SOURCE_REGION` and `S3_DEST_REGION`. List/Get run against the source region; Put runs against the destination region.

## Output

Per-file logs plus batch and overall summaries:

```
BATCH START batch=1/100 files=10
COPY OK   s3://src/a.log -> s3://dst/a.log | http_status=200 bytes=6698862
BATCH DONE  batch=1/100 sent=10 failed=0 bytes=66988620 elapsed=2.5s rate=4.00 files/s
BATCH WAIT  sleeping 5s before batch 2
...
COPY SUMMARY total=1000 copied=1000 failed=0 bytes=... batches=100 elapsed=10m rate=1.67 files/s
```
