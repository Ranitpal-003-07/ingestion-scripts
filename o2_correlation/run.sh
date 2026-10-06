#!/usr/bin/env bash
# Continuous correlation ingest → OpenObserve AP1 Cloud
# Usage:
#   ./run.sh              # continuous until Ctrl-C
#   ./run.sh --once       # single batch then exit
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and fill O2_* credentials." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip >/dev/null 2>&1 || true
pip install -q -r requirements.txt

# Parent of this package must be on PYTHONPATH (ingestion-scripts/)
export PYTHONPATH="${ROOT}/..${PYTHONPATH:+:$PYTHONPATH}"

exec python ingest_all.py "$@"
