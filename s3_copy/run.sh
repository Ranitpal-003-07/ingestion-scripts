#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_SERVICE_NAME=s3_copy \
OTEL_EXPORTER_OTLP_ENDPOINT=https://staging.ctrlb.dev/engine/api/default \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://staging.ctrlb.dev/engine/api/default/s3_copy/_otel/v1/logs \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic YOUR_API_TOKEN,stream-name=s3_copy" \
S3_SOURCE_BUCKET=ctrlb-5tb-benchmark-logs-public \
S3_DEST_BUCKET=testing-poc-sqs-blob-uploader \
S3_SOURCE_REGION=ap-south-1 \
S3_DEST_REGION=eu-north-1 \
go run .
