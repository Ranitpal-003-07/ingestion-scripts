#!/usr/bin/env bash
# CtrlB Flask guide — traces only.
#
#   OTEL_EXPORTER=otlp \
#   OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
#   OTEL_SERVICE_NAME=<service_name> \
#   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://<INGESTION_HOST>/api/default/v1/traces \
#   OTEL_METRICS_EXPORTER=none \
#   OTEL_LOGS_EXPORTER=none \
#   OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <API_TOKEN>,stream-name=<STREAM_NAME>" \
#   opentelemetry-instrument flask run -p 8080 --no-reload
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif ! python3 -c "import flask" 2>/dev/null; then
  echo "Flask not found. Create the venv and install deps first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && opentelemetry-bootstrap -a install" >&2
  exit 1
fi

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

PORT="${PORT:-8080}"
export FLASK_APP="${FLASK_APP:-app.py}"

export OTEL_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME="${STREAM_NAME}"
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://${INGESTION_HOST}/api/default/v1/traces"
export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${API_TOKEN},stream-name=${STREAM_NAME}"
unset OTEL_EXPORTER_OTLP_ENDPOINT 2>/dev/null || true
unset OTEL_EXPORTER_OTLP_LOGS_ENDPOINT 2>/dev/null || true

echo "flask_instrumentation_test (CtrlB Flask guide — traces only)"
echo "  OTEL_SERVICE_NAME=${OTEL_SERVICE_NAME}"
echo "  OTEL_METRICS_EXPORTER=${OTEL_METRICS_EXPORTER}"
echo "  OTEL_LOGS_EXPORTER=${OTEL_LOGS_EXPORTER}"
echo "  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT}"
echo "  launcher: opentelemetry-instrument flask run -p ${PORT} --no-reload"
echo

exec opentelemetry-instrument flask run -p "${PORT}" --no-reload
