#!/usr/bin/env python3
"""Ingest correlation demo logs, traces, and metrics into OpenObserve Cloud."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*")

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from o2_correlation import config, scenarios
from o2_correlation.logs import send_logs
from o2_correlation.metrics import MetricsSession
from o2_correlation.traces import TraceSession

logger = logging.getLogger(__name__)
_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    logger.info("Shutdown requested (%s) — finishing current tick…", signum)
    _shutdown = True


def emit_tick(
    *,
    do_logs: bool,
    do_traces: bool,
    do_metrics: bool,
    trace_session: TraceSession | None,
    metrics_session: MetricsSession | None,
) -> tuple[int, int]:
    n_traces = 0
    if do_logs:
        send_logs()
    if do_traces and trace_session is not None:
        ids = trace_session.emit_all()
        trace_session.flush()
        n_traces = len(ids)
    if do_metrics and metrics_session is not None:
        metrics_session.record_all()
        metrics_session.flush()
    return len(scenarios.active_workloads()) if do_logs else 0, n_traces


def run_once(
    *,
    do_logs: bool,
    do_traces: bool,
    do_metrics: bool,
) -> None:
    trace_session = TraceSession() if do_traces else None
    metrics_session = MetricsSession() if do_metrics else None
    try:
        n_logs, n_traces = emit_tick(
            do_logs=do_logs,
            do_traces=do_traces,
            do_metrics=do_metrics,
            trace_session=trace_session,
            metrics_session=metrics_session,
        )
        if do_metrics and metrics_session is not None:
            time.sleep(1.2)
            metrics_session.flush()
        logger.info(
            "Once complete: log_workloads=%s log_streams=%s traces=%s metric_streams=%s",
            n_logs,
            config.O2_LOG_STREAMS if do_logs else [],
            n_traces,
            config.O2_METRICS_STREAMS if do_metrics else [],
        )
        logger.info(
            "UI: https://ap1.openobserve.ai — Logs/Traces stream=default; "
            "Metrics=container_cpu, http_requests_total"
        )
    finally:
        if trace_session is not None:
            trace_session.shutdown()
        if metrics_session is not None:
            metrics_session.shutdown()


def run_loop(
    *,
    do_logs: bool,
    do_traces: bool,
    do_metrics: bool,
) -> None:
    trace_session = TraceSession() if do_traces else None
    metrics_session = MetricsSession() if do_metrics else None
    ticks = 0
    errors = 0
    try:
        services = ", ".join(
            f"{w.service}×{w.logs_per_tick}"
            + (f" (~{int(w.active_for_seconds)}s)" if w.active_for_seconds else "")
            for w in scenarios.WORKLOADS
        )
        logger.info(
            "Continuous ingest started → %s org=%s "
            "(logs=%s traces=%s metrics=%s) ticks/sec=%s  Ctrl-C to stop",
            config.O2_BASE_URL,
            config.O2_ORG,
            config.O2_LOG_STREAMS if do_logs else "-",
            config.O2_TRACE_STREAMS if do_traces else "-",
            config.O2_METRICS_STREAMS if do_metrics else "-",
            config.TICKS_PER_SECOND,
        )
        logger.info("Services (logs/tick): %s", services)
        logger.info("Open UI: https://ap1.openobserve.ai  (AP1 region, not cloud.openobserve.ai)")
        shipping_stopped_logged = False
        while not _shutdown:
            loop_start = time.time()
            for _ in range(config.TICKS_PER_SECOND):
                if _shutdown:
                    break
                try:
                    emit_tick(
                        do_logs=do_logs,
                        do_traces=do_traces,
                        do_metrics=do_metrics,
                        trace_session=trace_session,
                        metrics_session=metrics_session,
                    )
                    ticks += 1
                except Exception:
                    errors += 1
                    logger.exception("Ingest tick failed")
            if (
                not shipping_stopped_logged
                and scenarios.ingest_elapsed_seconds() >= scenarios.SHIPPING_ACTIVE_SECONDS
            ):
                shipping_stopped_logged = True
                logger.info(
                    "Shipping stopped after %.0fs — GROUP BY service will drop "
                    "shipping from recent windows while checkout/payments stay high, auth low",
                    scenarios.SHIPPING_ACTIVE_SECONDS,
                )
            elapsed = time.time() - loop_start
            time.sleep(max(0.0, 1.0 - elapsed))
            if ticks and ticks % 10 == 0:
                active = [w.service for w in scenarios.active_workloads()]
                logger.info(
                    "Running… ticks=%s errors=%s active_services=%s",
                    ticks,
                    errors,
                    active,
                )
    finally:
        logger.info("Stopping… total ticks=%s errors=%s", ticks, errors)
        if trace_session is not None:
            trace_session.shutdown()
        if metrics_session is not None:
            metrics_session.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest synthetic correlation demo data into OpenObserve Cloud"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single tick then exit (default is continuous until Ctrl-C)",
    )
    parser.add_argument(
        "--ticks-per-second",
        type=int,
        default=None,
        help="Ingest ticks per second in loop mode (default from TICKS_PER_SECOND)",
    )
    parser.add_argument("--logs-only", action="store_true")
    parser.add_argument("--traces-only", action="store_true")
    parser.add_argument("--metrics-only", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # Quiet noisy OTEL exporter internals
    logging.getLogger("opentelemetry.exporter.otlp").setLevel(logging.ERROR)
    logging.getLogger("opentelemetry.sdk").setLevel(logging.ERROR)

    config.validate_config()
    config.configure_ticks_per_second(args.ticks_per_second)

    only_flags = [args.logs_only, args.traces_only, args.metrics_only]
    if sum(only_flags) > 1:
        raise SystemExit("Use at most one of --logs-only, --traces-only, --metrics-only")

    do_logs = do_traces = do_metrics = True
    if args.logs_only:
        do_logs, do_traces, do_metrics = True, False, False
    elif args.traces_only:
        do_logs, do_traces, do_metrics = False, True, False
    elif args.metrics_only:
        do_logs, do_traces, do_metrics = False, False, True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if args.once:
        run_once(do_logs=do_logs, do_traces=do_traces, do_metrics=do_metrics)
    else:
        run_loop(do_logs=do_logs, do_traces=do_traces, do_metrics=do_metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
