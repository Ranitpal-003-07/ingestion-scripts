#!/usr/bin/env python3
"""
Ingest synthetic WAF nested logs into New Relic via the Log API.

Reuses the same rich WAF payloads as ingest_logs.py (generate_waf_match).

Environment:
  NEW_RELIC_LICENSE_KEY   Required ingest license key
  LOGS_PER_SECOND         Logs per second (default: 30, max: 200)
  DEPLOYMENT_ENV          deployment.environment on each log (default: demo)
  LOG_API_ENDPOINT        Default: https://log-api.newrelic.com/log/v1
                          EU: https://log-api.eu.newrelic.com/log/v1
  NR_LOG_SERVICE          service.name attribute (default: demo-waf-ingest)

Usage:
  pip install -r requirements.txt
  export NEW_RELIC_LICENSE_KEY="..."
  python ingest_nr_logs.py              # continuous ingestion (30 logs/sec)
  python ingest_nr_logs.py --rate 50    # override env/default rate
  python ingest_nr_logs.py --once -v    # single batch smoke test

Verification (after 2-5 minutes in New Relic Logs UI or NRQL):
  SELECT count(*) FROM Log
  WHERE service.name = 'demo-waf-ingest' SINCE 30 minutes ago

  SELECT count(*) FROM Log
  WHERE waf.action = 'BLOCK' SINCE 30 minutes ago
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

import requests

from ingest_logs import generate_waf_match
from nr_traces import config

logger = logging.getLogger(__name__)

DEFAULT_LOGS_PER_SECOND = 30
MAX_LOGS_PER_SECOND = 200
LOGS_PER_SECOND = DEFAULT_LOGS_PER_SECOND

LOG_API_ENDPOINT = config._clean_env(
    os.environ.get("LOG_API_ENDPOINT", "https://log-api.newrelic.com/log/v1")
).rstrip("/")
NR_LOG_SERVICE = config._clean_env(
    os.environ.get("NR_LOG_SERVICE", "demo-waf-ingest")
) or "demo-waf-ingest"

_shutdown = False


def configure_logs_per_second(cli_rate: int | None = None) -> int:
    """Resolve rate from --rate, then LOGS_PER_SECOND env, then default."""
    global LOGS_PER_SECOND

    if cli_rate is not None:
        raw = str(cli_rate)
        source = "--rate"
    else:
        raw = os.environ.get("LOGS_PER_SECOND", str(DEFAULT_LOGS_PER_SECOND))
        source = (
            "LOGS_PER_SECOND env"
            if "LOGS_PER_SECOND" in os.environ
            else "default"
        )

    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid logs/sec from {source}: {raw!r} (must be an integer)"
        ) from exc

    if value < 1:
        raise SystemExit(f"Logs per second must be >= 1, got {value} from {source}")

    if value > MAX_LOGS_PER_SECOND:
        logging.warning(
            "%s=%s is very high; capping at %s logs/sec. "
            "Unset LOGS_PER_SECOND or use: python ingest_nr_logs.py --rate 30",
            source,
            value,
            MAX_LOGS_PER_SECOND,
        )
        value = MAX_LOGS_PER_SECOND

    LOGS_PER_SECOND = value
    return value


def to_nr_log_event(waf: dict) -> dict:
    """Map a WAF match dict to a New Relic Log API event."""
    http = waf.get("httprequest") or {}
    ts_us = waf.get("timestamp") or waf.get("ctrlb_timestamp") or 0
    return {
        "timestamp": int(ts_us) // 1000,
        "message": (
            f"WAF {waf.get('action')} {http.get('httpmethod')} {http.get('uri')}"
        ),
        "logtype": "waf",
        "service.name": NR_LOG_SERVICE,
        "deployment.environment": config.DEPLOYMENT_ENV,
        "waf": waf,
    }


def _handle_signal(signum, frame) -> None:
    global _shutdown
    logger.info("Shutdown requested (%s)", signum)
    _shutdown = True


def send_batch(session: requests.Session, batch: list[dict]) -> bool:
    """POST a batch of log events to the New Relic Log API."""
    try:
        response = session.post(
            LOG_API_ENDPOINT,
            json=batch,
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("Network error sending logs: %s", exc)
        return False

    if response.status_code in (200, 202):
        logger.debug("Successfully sent %s log events", len(batch))
        return True

    logger.warning(
        "Failed to send logs: status=%s body=%s",
        response.status_code,
        response.text[:500],
    )
    return False


def run_once(session: requests.Session) -> None:
    batch = [to_nr_log_event(generate_waf_match()) for _ in range(LOGS_PER_SECOND)]
    if send_batch(session, batch):
        logger.info("Emitted %s WAF log events to New Relic", len(batch))
    else:
        logger.error("Failed to emit log batch")


def run_loop(session: requests.Session) -> None:
    logger.info(
        "Starting New Relic WAF log ingestion (%s logs/sec, service=%s, env=%s)",
        LOGS_PER_SECOND,
        NR_LOG_SERVICE,
        config.DEPLOYMENT_ENV,
    )
    sent = 0
    errors = 0
    interval_start = time.time()

    while not _shutdown:
        loop_start = time.time()
        batch = [to_nr_log_event(generate_waf_match()) for _ in range(LOGS_PER_SECOND)]

        if send_batch(session, batch):
            sent += len(batch)
        else:
            errors += 1

        now = time.time()
        if now - interval_start >= 10:
            logger.info(
                "Sent %s log events (%s failed batches in last interval)",
                sent,
                errors,
            )
            sent = 0
            errors = 0
            interval_start = now

        elapsed = time.time() - loop_start
        time.sleep(max(0, 1.0 - elapsed))

    logger.info("Ingestion stopped")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest synthetic WAF logs into New Relic via the Log API"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Send one batch and exit (smoke test)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=None,
        metavar="N",
        help=(
            f"Logs per second (default {DEFAULT_LOGS_PER_SECOND}, "
            f"max {MAX_LOGS_PER_SECOND})"
        ),
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
    configure_logs_per_second(args.rate)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    session = requests.Session()
    session.headers.update(
        {
            "Api-Key": config.LICENSE_KEY,
            "Content-Type": "application/json",
        }
    )

    if args.once:
        run_once(session)
    else:
        run_loop(session)

    return 0


if __name__ == "__main__":
    sys.exit(main())
