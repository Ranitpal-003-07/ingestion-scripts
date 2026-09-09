#!/usr/bin/env python3
"""
Ingest synthetic OpenTelemetry metrics for PromQL alert testing.

Environment:
  STREAM_NAME                  CtrlB metrics stream (stream-name header)
  OTEL_EXPORTER_OTLP_ENDPOINT  CtrlB base (.../engine/api/default)
  OTEL_EXPORTER_OTLP_HEADERS   Optional extra headers
  METRICS_EXPORT_INTERVAL_SECONDS  OTLP export interval (default: 5)
  METRICS_TICKS_PER_SECOND         Emission ticks per second (default: 1)
  DEPLOYMENT_ENV               deployment.environment (default: demo)

Usage:
  pip install -r requirements.txt
  export OTEL_EXPORTER_OTLP_ENDPOINT="https://staging.ctrlb.dev/engine/api/default"
  export STREAM_NAME="your_metrics_stream"
  python ingest_metrics.py --mode baseline
  python ingest_metrics.py --mode spike_cpu --target service=demo-api
  python ingest_metrics.py --mode spike_errors --hold-seconds 120
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import signal
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nr_metrics import config, scenarios
from nr_metrics.otlp import OtlpMetricsSession

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    logger.info("Shutdown requested (%s), flushing exporters...", signum)
    _shutdown = True


def run_once(session: OtlpMetricsSession, state: scenarios.ScenarioState) -> None:
    scenarios.emit_tick(session, state)
    logger.info("Emitted one metrics tick (mode=%s, target=%s)", state.mode, state.target or "all")


def run_loop(
    session: OtlpMetricsSession,
    state: scenarios.ScenarioState,
    *,
    hold_seconds: int | None = None,
) -> None:
    logger.info(
        "Starting OTLP metrics ingestion to %s (mode=%s, target=%s, ticks/sec=%s, stream=%s)",
        config.resolve_metrics_endpoint(),
        state.mode,
        state.target or "all",
        config.TICKS_PER_SECOND,
        config.STREAM_NAME or "-",
    )

    started_at = time.time()
    ticks = 0
    errors = 0
    interval_start = time.time()

    while not _shutdown:
        if hold_seconds is not None and (time.time() - started_at) >= hold_seconds:
            if state.mode != "baseline":
                logger.info(
                    "Hold period (%ss) elapsed; switching to baseline (recover)",
                    hold_seconds,
                )
                state.set_mode("baseline")
                started_at = time.time()

        loop_start = time.time()

        for _ in range(config.TICKS_PER_SECOND):
            if _shutdown:
                break
            try:
                scenarios.emit_tick(session, state)
                ticks += 1
            except Exception:
                errors += 1
                logger.exception("Failed to emit metrics tick")

        now = time.time()
        if now - interval_start >= 10:
            logger.info("Emitted %s metric ticks (%s errors in last interval)", ticks, errors)
            ticks = 0
            errors = 0
            interval_start = now

        elapsed = time.time() - loop_start
        sleep_for = max(0, 1.0 - elapsed)
        if sleep_for:
            time.sleep(sleep_for)

    session.flush()
    logger.info("Metrics ingestion stopped")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest synthetic Prometheus-style OTLP metrics for PromQL alert testing"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Emit a single metrics tick and exit (smoke test)",
    )
    parser.add_argument(
        "--mode",
        choices=scenarios.MODES,
        default="baseline",
        help="Scenario mode controlling which series breach thresholds",
    )
    parser.add_argument(
        "--target",
        default=None,
        metavar="KEY=VALUE",
        help="Limit breach to one service or instance (e.g. service=demo-api, instance=demo-api-1)",
    )
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=None,
        metavar="N",
        help="After N seconds in a spike/down mode, auto-switch to baseline (recover)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        metavar="SECONDS",
        help=f"OTLP export interval in seconds (default {config.DEFAULT_EXPORT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=None,
        metavar="N",
        help=f"Metric emission ticks per second (default {config.DEFAULT_TICKS_PER_SECOND})",
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
    config.configure_export_interval(args.interval)
    config.configure_ticks_per_second(args.rate)
    target = config.parse_target(args.target)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    state = scenarios.ScenarioState(mode=args.mode, target=target)
    session = OtlpMetricsSession()
    try:
        if args.once:
            run_once(session, state)
        else:
            run_loop(session, state, hold_seconds=args.hold_seconds)
    finally:
        session.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
