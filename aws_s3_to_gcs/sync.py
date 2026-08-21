#!/usr/bin/env python3
"""Copy objects from an AWS S3 bucket to a GCP Cloud Storage bucket.

AWS auth: VM IAM role / instance profile (or default boto3 credential chain).
GCP auth: service account JSON via GOOGLE_APPLICATION_CREDENTIALS.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from google.api_core.exceptions import Forbidden
from google.cloud import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aws_s3_to_gcs")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        log.error("Missing required env var: %s", name)
        sys.exit(1)
    return value


def join_prefix(prefix: str, key: str) -> str:
    prefix = prefix.strip("/")
    key = key.lstrip("/")
    if not prefix:
        return key
    return f"{prefix}/{key}"


def list_s3_keys(s3_client, bucket: str, prefix: str):
    paginator = s3_client.get_paginator("list_objects_v2")
    kwargs = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix

    for page in paginator.paginate(**kwargs):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Skip "folder" placeholder keys
            if key.endswith("/") and obj.get("Size", 0) == 0:
                continue
            yield key, obj.get("Size", 0)


def gcs_blob_exists(bucket, name: str) -> bool | None:
    """Return True/False if the object exists, or None if we cannot check (e.g. no get perm)."""
    try:
        return bucket.blob(name).exists()
    except Forbidden:
        return None


def copy_object(
    s3_client,
    gcs_bucket,
    source_bucket: str,
    source_key: str,
    dest_key: str,
    size: int,
    dry_run: bool,
) -> None:
    if dry_run:
        log.info("[dry-run] s3://%s/%s -> gs://%s/%s (%s bytes)",
                 source_bucket, source_key, gcs_bucket.name, dest_key, size)
        return

    log.info("Copying s3://%s/%s -> gs://%s/%s (%s bytes)",
             source_bucket, source_key, gcs_bucket.name, dest_key, size)

    body = s3_client.get_object(Bucket=source_bucket, Key=source_key)["Body"]
    blob = gcs_bucket.blob(dest_key)
    blob.upload_from_file(body, rewind=False)


def main() -> int:
    load_dotenv()

    aws_region = os.getenv("AWS_REGION", "ap-south-1").strip()
    source_bucket = require_env("AWS_SOURCE_BUCKET")
    source_prefix = os.getenv("AWS_SOURCE_PREFIX", "").strip()
    dest_bucket_name = require_env("GCP_DEST_BUCKET")
    dest_prefix = os.getenv("GCP_DEST_PREFIX", "").strip()
    creds_path = require_env("GOOGLE_APPLICATION_CREDENTIALS")
    # Default false: write-only SAs often lack storage.objects.get needed for exists checks.
    skip_existing = env_bool("SKIP_EXISTING", False)
    dry_run = env_bool("DRY_RUN", False)

    creds_file = Path(creds_path)
    if not creds_file.is_file():
        log.error("GCP credentials file not found: %s", creds_file.resolve())
        return 1

    # Ensure the Google client libraries pick up the same path
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_file.resolve())

    log.info("AWS region=%s source=s3://%s/%s", aws_region, source_bucket, source_prefix)
    log.info("GCP dest=gs://%s/%s skip_existing=%s dry_run=%s",
             dest_bucket_name, dest_prefix, skip_existing, dry_run)

    s3 = boto3.client("s3", region_name=aws_region)
    gcs = storage.Client.from_service_account_json(str(creds_file.resolve()))
    # Use bucket() not get_bucket() — get_bucket needs storage.buckets.get;
    # object uploaders often only have object-level roles.
    gcs_bucket = gcs.bucket(dest_bucket_name)

    copied = skipped = failed = 0

    try:
        keys = list(list_s3_keys(s3, source_bucket, source_prefix))
    except ClientError as exc:
        log.error("Failed to list AWS bucket %s: %s", source_bucket, exc)
        return 1

    if not keys:
        log.info("No objects found under s3://%s/%s", source_bucket, source_prefix)
        return 0

    log.info("Found %d object(s) to process", len(keys))

    for source_key, size in keys:
        # Preserve relative path under the source prefix when applying dest prefix
        relative_key = source_key
        if source_prefix and source_key.startswith(source_prefix):
            relative_key = source_key[len(source_prefix):].lstrip("/")

        dest_key = join_prefix(dest_prefix, relative_key)

        try:
            if skip_existing:
                exists = gcs_blob_exists(gcs_bucket, dest_key)
                if exists is None:
                    log.warning(
                        "SKIP_EXISTING disabled: SA lacks storage.objects.get on gs://%s",
                        dest_bucket_name,
                    )
                    skip_existing = False
                elif exists:
                    log.info("Skip existing gs://%s/%s", dest_bucket_name, dest_key)
                    skipped += 1
                    continue

            copy_object(
                s3_client=s3,
                gcs_bucket=gcs_bucket,
                source_bucket=source_bucket,
                source_key=source_key,
                dest_key=dest_key,
                size=size,
                dry_run=dry_run,
            )
            copied += 1
        except Exception as exc:  # noqa: BLE001 - keep copying remaining objects
            failed += 1
            log.exception("Failed %s: %s", source_key, exc)

    log.info("Done. copied=%d skipped=%d failed=%d", copied, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
