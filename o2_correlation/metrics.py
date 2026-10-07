"""OTLP/HTTP metrics export for correlation demo workloads.

One MeterProvider per workload so resource service.name matches the workload
(not a fake generator name). Labels use the same flat keys as logs/traces.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from o2_correlation import config, scenarios

logger = logging.getLogger(__name__)


class _WorkloadMetricsBackend:
    """Metrics for one workload → one OpenObserve stream (via stream-name header)."""

    def __init__(self, stream_name: str, workload: scenarios.Workload) -> None:
        self.stream_name = stream_name
        self.workload = workload
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "cumulative"
        )
        endpoint = config.metrics_otlp_url()
        headers = config.build_otlp_headers(stream_name)

        self._exporter = OTLPMetricExporter(
            endpoint=endpoint, headers=headers, timeout=30
        )
        # Resource service.name MUST be the real service (checkout/cart), otherwise
        # discovery invents a phantom "o2-correlation-metrics" service.
        self._meter_provider = MeterProvider(
            resource=Resource.create(
                {
                    "service.name": workload.service,
                    "deployment.environment": workload.env,
                }
            ),
            metric_readers=[
                PeriodicExportingMetricReader(
                    self._exporter,
                    export_interval_millis=1000,
                )
            ],
        )
        meter = self._meter_provider.get_meter("o2-correlation-demo")

        self._lock = threading.Lock()
        self._cpu = 0.0
        self._requests = 0.0
        self._attrs = scenarios.build_metric_attributes(workload)

        def cpu_callback(options):  # noqa: ANN001
            from opentelemetry.metrics import Observation

            with self._lock:
                return [Observation(self._cpu, dict(self._attrs))]

        def requests_callback(options):  # noqa: ANN001
            from opentelemetry.metrics import Observation

            with self._lock:
                return [Observation(self._requests, dict(self._attrs))]

        meter.create_observable_gauge(
            name="container_cpu",
            callbacks=[cpu_callback],
            description="CPU usage ratio for correlation demo",
        )
        meter.create_observable_gauge(
            name="http_requests_total",
            callbacks=[requests_callback],
            description="Request count snapshot for correlation demo",
        )

    def record(self) -> None:
        with self._lock:
            self._cpu = scenarios.metric_cpu_ratio(self.workload)
            self._requests = float(scenarios.metric_request_count(self.workload))

    def flush(self) -> None:
        self._meter_provider.force_flush()

    def shutdown(self) -> None:
        self.flush()
        self._meter_provider.shutdown()


class MetricsSession:
    """Emit metrics for every workload × every configured metrics stream."""

    def __init__(self, stream_names: list[str] | None = None) -> None:
        names = stream_names if stream_names is not None else config.O2_METRICS_STREAMS
        self._backends = [
            _WorkloadMetricsBackend(stream, workload)
            for stream in names
            for workload in scenarios.WORKLOADS
        ]

    def record_all(self) -> None:
        active_ids = {w.workload_id for w in scenarios.active_workloads()}
        for backend in self._backends:
            if backend.workload.workload_id in active_ids:
                backend.record()

    def flush(self) -> None:
        for backend in self._backends:
            backend.flush()

    def shutdown(self) -> None:
        for backend in self._backends:
            backend.shutdown()


def send_metrics() -> None:
    session = MetricsSession()
    try:
        session.record_all()
        session.flush()
        time.sleep(1.2)
        session.flush()
        logger.info(
            "Ingested metrics for %s workloads × %s stream(s) at %s",
            len(scenarios.WORKLOADS),
            len(config.O2_METRICS_STREAMS),
            config.metrics_otlp_url(),
        )
    finally:
        session.shutdown()
