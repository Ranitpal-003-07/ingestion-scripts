# AWS S3 → GCP Cloud Storage sync

Copies objects from an AWS S3 bucket into a GCP Cloud Storage bucket.

- **AWS auth**: VM IAM role / instance profile (default boto3 chain)
- **GCP auth**: service account JSON key

## Setup

```bash
cd aws_s3_to_gcs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Put your GCP service account key next to the script, e.g. gcp-sa.json
```

Edit `.env`:

```bash
AWS_REGION=ap-south-1
AWS_SOURCE_BUCKET=my-aws-source-bucket
# AWS_SOURCE_PREFIX=optional/source/prefix/

GCP_DEST_BUCKET=my-gcp-dest-bucket
# GCP_DEST_PREFIX=optional/dest/prefix/
GOOGLE_APPLICATION_CREDENTIALS=./gcp-sa.json

# SKIP_EXISTING=true
# DRY_RUN=false
```

## Run

```bash
# Preview what would be copied
DRY_RUN=true python sync.py

# Copy
python sync.py
```

## Behaviour

| Setting | Effect |
|---------|--------|
| `AWS_SOURCE_PREFIX` | Only list/copy keys under this prefix in the AWS bucket |
| `GCP_DEST_PREFIX` | Prepend this path in the GCP bucket |
| `SKIP_EXISTING` | Skip objects that already exist in GCP (default `false`; needs `storage.objects.get`) |
| `DRY_RUN` | Log planned copies without uploading |

Example:

- Source: `s3://aws-bucket/logs/2026/a.json`
- `AWS_SOURCE_PREFIX=logs/`
- `GCP_DEST_PREFIX=from-aws/`
- Result: `gs://gcp-bucket/from-aws/2026/a.json`

## VM permissions

**AWS (instance role):** `s3:ListBucket` on the source bucket, `s3:GetObject` on the objects.

**GCP (service account):** `storage.objects.create` is enough to upload. `SKIP_EXISTING=true` also needs `storage.objects.get`. Bucket-level `storage.buckets.get` is **not** required.
