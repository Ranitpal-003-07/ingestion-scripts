#!/usr/bin/env bash
# CtrlB Flask guide env + Gunicorn gevent (fork-safe).
# Same OTEL_* as run.sh — monkey-patch in gunicorn_gevent.conf.py post_fork.
#
#   OTEL_EXPORTER=otlp \
#   OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
#   OTEL_SERVICE_NAME=<service_name> \
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://<INGESTION_HOST>/api/default \
#   OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://<INGESTION_HOST>/api/default/<STREAM_NAME>/_otel/v1/logs \
#   OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <API_TOKEN>,stream-name=<STREAM_NAME>" \
#   gunicorn -c gunicorn_gevent.conf.py app:app
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

if ! python3 -c "import gunicorn, gevent" 2>/dev/null; then
  echo "Installing gunicorn + gevent..."
  pip install -q gunicorn gevent
fi

# macOS: avoid ObjC fork crashes with multi-worker Gunicorn
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

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
export PORT

# Same OTEL env as ./run.sh
export OTEL_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME="${STREAM_NAME}"
export OTEL_EXPORTER_OTLP_ENDPOINT="https://${INGESTION_HOST}/api/default"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="https://${INGESTION_HOST}/api/default/${STREAM_NAME}/_otel/v1/logs"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${API_TOKEN},stream-name=${STREAM_NAME}"

echo "flask_instrumentation_test (CtrlB Flask guide — Gunicorn gevent)"
echo "  OTEL_SERVICE_NAME=${OTEL_SERVICE_NAME}"
echo "  OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT}"
echo "  launcher: gunicorn -c gunicorn_gevent.conf.py app:app"
echo

exec gunicorn -c gunicorn_gevent.conf.py app:app
