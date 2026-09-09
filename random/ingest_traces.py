#!/usr/bin/env python3
"""
Ingest synthetic OpenTelemetry traces (and optional metrics) to OTLP backends.
Defaults to New Relic; target CtrlB via endpoint + STREAM_NAME / headers.

Environment:
  NEW_RELIC_LICENSE_KEY   New Relic ingest key (required only for NR)
  STREAM_NAME             CtrlB stream (sent as stream-name header)
  OTEL_EXPORTER_OTLP_ENDPOINT  NR default or CtrlB base (.../engine/api/default)
  OTEL_EXPORTER_OTLP_HEADERS   Optional extra headers
  TRACES_PER_SECOND       Traces per second (default: 5, max: 100)
  DEPLOYMENT_ENV          deployment.environment (default: demo)
  OTLP_DISABLE_METRICS    Default on for CtrlB; set 0 to enable metrics export

Usage:
  pip install -r requirements.txt
  # New Relic
  export NEW_RELIC_LICENSE_KEY="..."
  python ingest_traces.py --once

  # CtrlB (no Authorization required; stream via header)
  export OTEL_EXPORTER_OTLP_ENDPOINT="https://staging.ctrlb.dev/engine/api/default"
  export STREAM_NAME="your_traces_stream"
  python3 ingest_traces.py --rate 5

CtrlB SQL smoke checks (replace <stream>):
  SELECT span_kind, COUNT(*) FROM "<stream>" GROUP BY span_kind ORDER BY 2 DESC;
  SELECT span_status, COUNT(*) FROM "<stream>" GROUP BY span_status;
  SELECT service_name, operation_name, COUNT(*) FROM "<stream>"
    WHERE span_kind = '2' OR span_kind = 'SPAN_KIND_SERVER'
    GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20;
  SELECT COALESCE(NULLIF(db_system_name,''), db_system) AS sys,
         COALESCE(NULLIF(db_operation_name,''), db_operation) AS op,
         COALESCE(NULLIF(db_sql_table,''), NULLIF(db_mongodb_collection,''),
                  NULLIF(db_namespace,''), db_name) AS target,
         COUNT(*) FROM "<stream>"
    WHERE span_kind = '3' OR span_kind = 'SPAN_KIND_CLIENT'
    GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 20;
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import signal
import sys
import time

# Allow running as: python random/ingest_traces.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nr_traces import config, scenarios
from nr_traces.otlp import OtlpSession

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    logger.info("Shutdown requested (%s), flushing exporters...", signum)
    _shutdown = True


def run_once(session: OtlpSession) -> None:
    trace_id = scenarios.emit_random(session)
    session.flush()
    logger.info("Emitted trace trace.id=%s", trace_id)


def run_loop(session: OtlpSession) -> None:
    logger.info(
        "Starting OTLP trace ingestion to %s (%s traces/sec, env=%s, stream=%s)",
        config.resolve_traces_endpoint(),
        config.TRACES_PER_SECOND,
        config.DEPLOYMENT_ENV,
        config.STREAM_NAME or "-",
    )
    emitted = 0
    errors = 0
    interval_start = time.time()

    while not _shutdown:
        loop_start = time.time()

        for _ in range(config.TRACES_PER_SECOND):
            if _shutdown:
                break
            try:
                trace_id = scenarios.emit_random(session)
                emitted += 1
                logger.debug("trace.id=%s", trace_id)
            except Exception:
                errors += 1
                logger.exception("Failed to emit trace")

        session.flush()

        now = time.time()
        if now - interval_start >= 10:
            logger.info("Emitted %s traces (%s errors in last interval)", emitted, errors)
            emitted = 0
            errors = 0
            interval_start = now

        elapsed = time.time() - loop_start
        time.sleep(max(0, 1.0 - elapsed))

    session.flush()
    logger.info("Ingestion stopped")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest synthetic APM traces into OTLP backend (New Relic/CtrlB/custom)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Emit a single trace and exit (smoke test)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=None,
        metavar="N",
        help=f"Traces per second (default {config.DEFAULT_TRACES_PER_SECOND}, max {config.MAX_TRACES_PER_SECOND})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config.validate_config()
    config.configure_traces_per_second(args.rate)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    session = OtlpSession()
    try:
        if args.once:
            run_once(session)
        else:
            run_loop(session)
    finally:
        session.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
