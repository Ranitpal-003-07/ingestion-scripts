#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif ! python3 -c "import django" 2>/dev/null; then
  echo "Django not found. Create the venv and install deps first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${PORT:-8081}"
export DJANGO_SETTINGS_MODULE=config.settings

python3 manage.py runserver "0.0.0.0:${PORT}" --noreload
