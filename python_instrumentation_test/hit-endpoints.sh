#!/usr/bin/env bash
# Hit health/roll/work repeatedly to generate traces, logs, and metrics.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
COUNT="${COUNT:-50}"

echo "Hitting ${BASE_URL} ({health,roll,work}) x ${COUNT}"
for i in $(seq 1 "${COUNT}"); do
  health="$(curl -sS -o /tmp/py_health.out -w "%{http_code}" "${BASE_URL}/health")"
  roll="$(curl -sS -o /tmp/py_roll.out -w "%{http_code}" "${BASE_URL}/roll")"
  work="$(curl -sS -o /tmp/py_work.out -w "%{http_code}" "${BASE_URL}/work")"
  echo "[${i}/${COUNT}] health=${health} roll=${roll}($(cat /tmp/py_roll.out)) work=${work}"
done
echo "done — wait ~15s then check CtrlB stream python_instrumentation_test"
echo "metrics: python.app.http.requests, python.app.dice.rolls, python.app.work.duration"
