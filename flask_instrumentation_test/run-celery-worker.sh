#!/usr/bin/env bash
# Clean Celery worker for CtrlB OTEL test — ignores stale shell OTEL_* from other demos.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Clear leftover exports from Gunicorn/ASGI/gevent tests
unset DJANGO_SETTINGS_MODULE || true
unset OTEL_SERVICE_NAME || true
unset OTEL_EXPORTER_OTLP_ENDPOINT || true
unset OTEL_EXPORTER_OTLP_HEADERS || true
unset OTEL_EXPORTER_OTLP_PROTOCOL || true
unset OTEL_TRACES_EXPORTER || true

export CELERY_FIXUP_DISABLE=1
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Load .env into this shell for sanity prints only; celery_app.py also loads it
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${INGESTION_HOST:?set INGESTION_HOST in .env}"
: "${STREAM_NAME:?set STREAM_NAME in .env}"
: "${API_TOKEN:?set API_TOKEN in .env}"

echo "Starting Celery worker"
echo "  STREAM_NAME=${STREAM_NAME}"
echo "  Look in CtrlB Traces → stream=${STREAM_NAME} → service=celery-fixed-test"
echo

exec celery -A celery_app worker --loglevel=INFO --concurrency=2
