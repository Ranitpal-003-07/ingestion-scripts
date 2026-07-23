#!/usr/bin/env bash
# CtrlB Flask guide env + Docker (same OTEL_* as run.sh).
#
#   docker run ... \
#     -e OTEL_EXPORTER=otlp \
#     -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
#     -e OTEL_SERVICE_NAME=<service_name> \
#     -e OTEL_EXPORTER_OTLP_ENDPOINT=https://<INGESTION_HOST>/api/default \
#     -e OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://<INGESTION_HOST>/api/default/<STREAM_NAME>/_otel/v1/logs \
#     -e OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <API_TOKEN>,stream-name=<STREAM_NAME>" \
#     flask-otel-test
set -euo pipefail
cd "$(dirname "$0")"

# Drop stale OTEL_* from other demos
unset DJANGO_SETTINGS_MODULE 2>/dev/null || true
while IFS= read -r var; do
  unset "$var" 2>/dev/null || true
done < <(env | awk -F= '/^OTEL_/ {print $1}')

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${INGESTION_HOST:?set INGESTION_HOST in .env}"
: "${STREAM_NAME:?set STREAM_NAME in .env}"
: "${API_TOKEN:?set API_TOKEN in .env}"

IMAGE="${IMAGE:-flask-otel-test}"
PORT="${PORT:-8080}"

# Same OTEL env as ./run.sh
export OTEL_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME="${STREAM_NAME}"
export OTEL_EXPORTER_OTLP_ENDPOINT="https://${INGESTION_HOST}/api/default"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="https://${INGESTION_HOST}/api/default/${STREAM_NAME}/_otel/v1/logs"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${API_TOKEN},stream-name=${STREAM_NAME}"

echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" .

echo
echo "flask_instrumentation_test (CtrlB Flask guide — Docker)"
echo "  OTEL_SERVICE_NAME=${OTEL_SERVICE_NAME}"
echo "  OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT}"
echo "  http://localhost:${PORT}"
echo "  CMD: opentelemetry-instrument python app.py"
echo

exec docker run --rm -p "${PORT}:8080" \
  -e OTEL_EXPORTER \
  -e OTEL_EXPORTER_OTLP_PROTOCOL \
  -e OTEL_SERVICE_NAME \
  -e OTEL_EXPORTER_OTLP_ENDPOINT \
  -e OTEL_EXPORTER_OTLP_LOGS_ENDPOINT \
  -e OTEL_EXPORTER_OTLP_HEADERS \
  -e PORT=8080 \
  "${IMAGE}"
