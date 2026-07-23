#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
COUNT="${COUNT:-50}"
echo "Hitting ${BASE_URL} ({health,roll,work}) x ${COUNT}"
for i in $(seq 1 "${COUNT}"); do
  health="$(curl -sS -o /tmp/django_health.out -w "%{http_code}" "${BASE_URL}/health")"
  roll="$(curl -sS -o /tmp/django_roll.out -w "%{http_code}" "${BASE_URL}/roll")"
  work="$(curl -sS -o /tmp/django_work.out -w "%{http_code}" "${BASE_URL}/work")"
  echo "[${i}/${COUNT}] health=${health} roll=${roll}($(cat /tmp/django_roll.out)) work=${work}"
done
echo "done — check CtrlB for django_instrumentation_test"
