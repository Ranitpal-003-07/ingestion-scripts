#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

unset DJANGO_SETTINGS_MODULE || true
export CELERY_FIXUP_DISABLE=1

python - <<'PY'
from celery_app import work_task

for i in range(5):
    r = work_task.delay(5)
    print(f"enqueued demo.work id={r.id}")
print("done — wait ~10s, then check CtrlB for service=celery-fixed-test")
PY
