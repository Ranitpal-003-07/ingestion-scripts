#!/usr/bin/env bash
# CtrlB Django guide — logs only (Step 3).
#
#   DJANGO_SETTINGS_MODULE=myproject.settings \
#   OTEL_EXPORTER=otlp \
#   OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
#   OTEL_SERVICE_NAME=<service_name> \
#   OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://<INGESTION_HOST>/api/default/<STREAM_NAME>/_otel/v1/logs \
#   OTEL_TRACES_EXPORTER=none \
#   OTEL_METRICS_EXPORTER=none \
#   OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <API_TOKEN>,stream-name=<STREAM_NAME>" \
#   opentelemetry-instrument python manage.py runserver --noreload
#
# Docs often use myproject.settings — this app uses config.settings.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif ! python3 -c "import django" 2>/dev/null; then
  echo "Django not found. Create the venv and install deps first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && opentelemetry-bootstrap -a install" >&2
  exit 1
fi

# Drop stale OTEL_* / settings from other demos
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

export DJANGO_SETTINGS_MODULE=config.settings
export OTEL_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME="${STREAM_NAME}"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="https://${INGESTION_HOST}/api/default/${STREAM_NAME}/_otel/v1/logs"
export OTEL_TRACES_EXPORTER=none
export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${API_TOKEN},stream-name=${STREAM_NAME}"
unset OTEL_EXPORTER_OTLP_ENDPOINT 2>/dev/null || true
unset OTEL_EXPORTER_OTLP_TRACES_ENDPOINT 2>/dev/null || true

echo "django_instrumentation_test (CtrlB Django guide — logs only)"
echo "  DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}"
echo "  OTEL_SERVICE_NAME=${OTEL_SERVICE_NAME}"
echo "  OTEL_TRACES_EXPORTER=${OTEL_TRACES_EXPORTER}"
echo "  OTEL_METRICS_EXPORTER=${OTEL_METRICS_EXPORTER}"
echo "  OTEL_LOGS_EXPORTER=${OTEL_LOGS_EXPORTER}"
echo "  OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT}"
echo "  launcher: opentelemetry-instrument python manage.py runserver 0.0.0.0:${PORT} --noreload"
echo

exec opentelemetry-instrument python manage.py runserver "0.0.0.0:${PORT}" --noreload
