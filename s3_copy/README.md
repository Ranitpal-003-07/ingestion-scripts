# s3_copy

Copy all objects from one S3 bucket to one or more destination buckets using the EC2 instance IAM role.
Uses **GetObject** on the source bucket and **PutObject** on each destination (data flows through the VM).

## Config

Copy the example and edit values:

```bash
cp .env.example .env
```

### One source → one destination

```bash
S3_SOURCE_BUCKET=source-bucket
S3_DEST_BUCKET=dest-bucket
S3_SOURCE_REGION=ap-south-1
S3_DEST_REGION=eu-north-1
```

### One source → multiple destinations

Use comma-separated buckets:

```bash
S3_SOURCE_BUCKET=source-bucket
S3_DEST_BUCKETS=dest-a,dest-b,dest-c
S3_SOURCE_REGION=ap-south-1
S3_DEST_REGION=eu-north-1
```

`S3_DEST_BUCKET` still works for a single bucket (and also accepts a comma list). Prefer `S3_DEST_BUCKETS` when fan-out is intentional.

For **per-destination regions**, set matching lists:

```bash
S3_DEST_BUCKETS=dest-a,dest-b
S3_DEST_REGIONS=eu-north-1,us-east-1
```

If `S3_DEST_REGIONS` is omitted, every dest uses `S3_DEST_REGION` (then `AWS_REGION`, then the source region).

Optional in `.env`:

```bash
S3_PREFIX=logs/2026/
S3_DEST_PREFIX=archive/                 # shared key prefix on every dest
# S3_DEST_PREFIXES=a/,b/,c/             # or one prefix per dest bucket
S3_COPY_WORKERS=10       # parallel transfers within each batch
S3_BATCH_SIZE=10         # files per batch before pausing
S3_BATCH_INTERVAL=5s     # wait between batches (e.g. 5s, 1m, 30s)
```

Each listed object is uploaded to **every** destination. Summary `copied` / `failed` counts are per put (objects × dests).

### Batch flow

1. Send up to `S3_BATCH_SIZE` files using `S3_COPY_WORKERS` in parallel (each file goes to all dests)
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
| `s3:PutObject` | `arn:aws:s3:::DEST-BUCKET/*` (each destination) |

Source and destination buckets may be in **different regions** — set `S3_SOURCE_REGION` and `S3_DEST_REGION` / `S3_DEST_REGIONS`. List/Get run against the source region; Put runs against each destination region.

## Output

Per-file logs plus batch and overall summaries:

```
BATCH START batch=1/100 files=10 dests=2
COPY OK   s3://src/a.log -> s3://dst-a/a.log | http_status=200 bytes=6698862
COPY OK   s3://src/a.log -> s3://dst-b/a.log | http_status=200 bytes=6698862
BATCH DONE  batch=1/100 sent=20 failed=0 bytes=... elapsed=2.5s rate=8.00 files/s
...
COPY SUMMARY objects=1000 dests=2 puts=2000 copied=2000 failed=0 bytes=... batches=100 elapsed=10m rate=...
```
