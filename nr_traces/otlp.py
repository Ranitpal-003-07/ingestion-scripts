"""OTLP exporters and per-service tracers for New Relic/CtrlB/custom backends."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from nr_traces import config

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.metrics import Meter
    from opentelemetry.trace import Tracer


class OtlpSession:
    """Manages OTLP trace/metric export for all demo services."""

    def __init__(self) -> None:
        headers = config.build_otlp_headers()
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "delta"
        )

        self._span_exporters: list[OTLPSpanExporter] = []
        traces_endpoint = (
            config.OTLP_TRACES_ENDPOINT or f"{config.OTLP_ENDPOINT}/v1/traces"
        )
        metrics_endpoint = (
            config.OTLP_METRICS_ENDPOINT or f"{config.OTLP_ENDPOINT}/v1/metrics"
        )
        self._metric_exporter: OTLPMetricExporter | None = None
        if not config.OTLP_DISABLE_METRICS:
            self._metric_exporter = OTLPMetricExporter(
                endpoint=metrics_endpoint,
                headers=headers,
            )

        self._tracer_providers: list[TracerProvider] = []
        self._tracers: dict[str, Tracer] = {}

        for service_name in config.SERVICES:
            span_exporter = OTLPSpanExporter(
                endpoint=traces_endpoint,
                headers=headers,
            )
            self._span_exporters.append(span_exporter)
            resource = Resource.create(
                {
                    "service.name": service_name,
                    "service.instance.id": config.SERVICE_INSTANCE_ID,
                    "deployment.environment": config.DEPLOYMENT_ENV,
                }
            )
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(
                BatchSpanProcessor(
                    span_exporter,
                    schedule_delay_millis=500,
                )
            )
            self._tracer_providers.append(provider)
            self._tracers[service_name] = provider.get_tracer("nr-fake-apm")

        default_resource = Resource.create(
            {
                "service.name": "demo-api-gateway",
                "service.instance.id": config.SERVICE_INSTANCE_ID,
                "deployment.environment": config.DEPLOYMENT_ENV,
            }
        )
        metric_readers = []
        if self._metric_exporter is not None:
            metric_readers.append(
                PeriodicExportingMetricReader(
                    self._metric_exporter,
                    export_interval_millis=5000,
                )
            )
        self._meter_provider = MeterProvider(
            resource=default_resource,
            metric_readers=metric_readers,
        )
        metrics.set_meter_provider(self._meter_provider)
        self._meter = metrics.get_meter("nr-fake-apm")
        self._http_server_duration = self._meter.create_histogram(
            name="http.server.request.duration",
            unit="s",
            description="Duration of inbound HTTP requests",
        )
        self._http_client_duration = self._meter.create_histogram(
            name="http.client.request.duration",
            unit="s",
            description="Duration of outbound HTTP client calls",
        )
        self._messaging_process_duration = self._meter.create_histogram(
            name="messaging.process.duration",
            unit="s",
            description="Duration of messaging consumer processing",
        )

    def tracer(self, service_name: str) -> Tracer:
        return self._tracers[service_name]

    @staticmethod
    def parent_context(trace_id: int, parent_span_id: int) -> Context:
        span_context = SpanContext(
            trace_id=trace_id,
            span_id=parent_span_id,
            is_remote=True,
            trace_flags=TraceFlags(0x01),
        )
        return trace.set_span_in_context(NonRecordingSpan(span_context))

    def record_http_server(
        self,
        *,
        service_name: str,
        duration_s: float,
        method: str,
        route: str,
        status_code: int,
    ) -> None:
        self._http_server_duration.record(
            duration_s,
            attributes={
                "service.name": service_name,
                "http.request.method": method,
                "http.route": route,
                "http.response.status_code": status_code,
            },
        )

    def record_http_client(
        self,
        *,
        service_name: str,
        duration_s: float,
        method: str,
        url: str,
        status_code: int,
    ) -> None:
        self._http_client_duration.record(
            duration_s,
            attributes={
                "service.name": service_name,
                "http.request.method": method,
                "url.full": url,
                "http.response.status_code": status_code,
            },
        )

    def record_messaging_process(
        self,
        *,
        service_name: str,
        duration_s: float,
        system: str,
        destination: str,
    ) -> None:
        self._messaging_process_duration.record(
            duration_s,
            attributes={
                "service.name": service_name,
                "messaging.system": system,
                "messaging.destination.name": destination,
            },
        )

    def flush(self) -> None:
        for provider in self._tracer_providers:
            provider.force_flush()
        if self._metric_exporter is not None:
            self._meter_provider.force_flush()

    def shutdown(self) -> None:
        self.flush()
        for provider in self._tracer_providers:
            provider.shutdown()
        if self._metric_exporter is not None:
            self._meter_provider.shutdown()
        for exporter in self._span_exporters:
            exporter.shutdown()
        if self._metric_exporter is not None:
            self._metric_exporter.shutdown()
