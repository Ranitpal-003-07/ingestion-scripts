#!/usr/bin/env python3
"""
Ingest synthetic OpenTelemetry traces and metrics into New Relic (US OTLP).

Environment:
  NEW_RELIC_LICENSE_KEY   Required ingest license key
  TRACES_PER_SECOND       Traces per second (default: 5, max: 100)
  DEPLOYMENT_ENV          deployment.environment resource attr (default: demo)
  OTEL_EXPORTER_OTLP_ENDPOINT  Default: https://otlp.nr-data.net

Usage:
  pip install -r requirements.txt
  export NEW_RELIC_LICENSE_KEY="..."
  python ingest_traces.py              # continuous ingestion (5 traces/sec)
  python ingest_traces.py --rate 10    # override env/default rate
  python ingest_traces.py --once       # emit one trace and exit

Verification (after 2-5 minutes in New Relic):
  SELECT count(*) FROM Span
  WHERE service.name LIKE 'demo-%' SINCE 30 minutes ago

  SELECT count(*) FROM Span
  WHERE service.name = 'demo-api-gateway' AND transaction.name IS NOT NULL
  SINCE 30 minutes ago

  SELECT count(*) FROM Span WHERE error.message IS NOT NULL SINCE 30 minutes ago

  SELECT count(*) FROM Span WHERE db.system IS NOT NULL SINCE 30 minutes ago

UI: APM & Services -> filter demo-* OpenTelemetry services
  - Transactions, Databases, External services, Distributed tracing, Service map
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

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
        "Starting New Relic trace ingestion (%s traces/sec, env=%s)",
        config.TRACES_PER_SECOND,
        config.DEPLOYMENT_ENV,
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
        description="Ingest synthetic APM traces into New Relic via OTLP"
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
