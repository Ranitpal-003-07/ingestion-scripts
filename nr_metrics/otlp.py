"""OTLP metrics exporter for PromQL alert testing."""

from __future__ import annotations

import logging
import os
import threading

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

from nr_metrics import config

logger = logging.getLogger(__name__)


class OtlpMetricsSession:
    """Exports demo Prometheus-style metrics via OTLP HTTP."""

    def __init__(self) -> None:
        headers = config.build_otlp_headers()
        # PromQL rate()/increase() need monotonic cumulative counters, not deltas.
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "cumulative"
        )

        metrics_endpoint = config.resolve_metrics_endpoint()
        export_interval_ms = int(config.EXPORT_INTERVAL_SECONDS * 1000)

        logger.info(
            "OTLP metrics endpoint=%s interval=%ss headers=%s",
            metrics_endpoint,
            config.EXPORT_INTERVAL_SECONDS,
            {
                k: ("***" if k.lower() in ("authorization", "api-key") else v)
                for k, v in headers.items()
            },
        )

        self._metric_exporter = OTLPMetricExporter(
            endpoint=metrics_endpoint,
            headers=headers,
        )

        resource = Resource.create(
            {
                "service.name": "demo-metrics-generator",
                "deployment.environment": config.DEPLOYMENT_ENV,
            }
        )

        latency_view = View(
            instrument_name="demo_http_request_duration_seconds",
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=(
                    0.005,
                    0.01,
                    0.025,
                    0.05,
                    0.1,
                    0.25,
                    0.5,
                    1.0,
                    2.5,
                    5.0,
                    10.0,
                )
            ),
        )

        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[
                PeriodicExportingMetricReader(
                    self._metric_exporter,
                    export_interval_millis=export_interval_ms,
                )
            ],
            views=[latency_view],
        )
        metrics.set_meter_provider(self._meter_provider)
        meter = metrics.get_meter("demo-metrics-generator")

        self._lock = threading.Lock()
        self._gauge_values: dict[str, dict[tuple[tuple[str, str], ...], float]] = {
            "demo_up": {},
            "demo_cpu_usage_ratio": {},
            "demo_memory_usage_ratio": {},
        }

        def _make_gauge_callback(metric_name: str):
            def _callback(options):  # noqa: ANN001
                from opentelemetry.metrics import Observation

                with self._lock:
                    return [
                        Observation(value, dict(attr_items))
                        for attr_items, value in self._gauge_values[metric_name].items()
                    ]

            return _callback

        meter.create_observable_gauge(
            name="demo_up",
            callbacks=[_make_gauge_callback("demo_up")],
            description="1 if the demo instance is up, 0 if down",
        )
        meter.create_observable_gauge(
            name="demo_cpu_usage_ratio",
            callbacks=[_make_gauge_callback("demo_cpu_usage_ratio")],
            description="CPU usage ratio 0-1 for alert threshold tests",
        )
        meter.create_observable_gauge(
            name="demo_memory_usage_ratio",
            callbacks=[_make_gauge_callback("demo_memory_usage_ratio")],
            description="Memory usage ratio 0-1 for alert threshold tests",
        )

        self._requests = meter.create_counter(
            name="demo_http_requests_total",
            description="Total HTTP requests for rate() alert tests",
        )
        self._errors = meter.create_counter(
            name="demo_http_errors_total",
            description="Total HTTP errors for error-rate alert tests",
        )
        self._latency = meter.create_histogram(
            name="demo_http_request_duration_seconds",
            unit="s",
            description="HTTP request latency histogram for quantile alerts",
        )

    def _set_gauge(self, name: str, value: float, attributes: dict[str, str]) -> None:
        key = tuple(sorted(attributes.items()))
        with self._lock:
            self._gauge_values[name][key] = value

    def record_gauges(
        self,
        *,
        up: float,
        cpu_ratio: float,
        memory_ratio: float,
        attributes: dict[str, str],
    ) -> None:
        self._set_gauge("demo_up", up, attributes)
        self._set_gauge("demo_cpu_usage_ratio", cpu_ratio, attributes)
        self._set_gauge("demo_memory_usage_ratio", memory_ratio, attributes)

    def record_requests(self, count: int, *, attributes: dict[str, str]) -> None:
        self._requests.add(count, attributes)

    def record_errors(self, count: int, *, attributes: dict[str, str]) -> None:
        self._errors.add(count, attributes)

    def record_latency(self, seconds: float, *, attributes: dict[str, str]) -> None:
        self._latency.record(seconds, attributes)

    def flush(self) -> None:
        self._meter_provider.force_flush()

    def shutdown(self) -> None:
        self.flush()
        self._meter_provider.shutdown()
        self._metric_exporter.shutdown()
