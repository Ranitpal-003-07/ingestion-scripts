"""OTLP exporters and lazy per-(service, instance) tracers."""

from __future__ import annotations

import logging
import os
import random
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

from nr_traces import catalog, config

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.trace import Tracer

logger = logging.getLogger(__name__)


class _SharedSpanExporter:
    """Wraps one exporter so multiple BatchSpanProcessors don't shut it down."""

    def __init__(self, exporter: OTLPSpanExporter) -> None:
        self._exporter = exporter

    def export(self, spans):  # noqa: ANN001
        return self._exporter.export(spans)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis=timeout_millis)

    def shutdown(self) -> None:
        return None


class OtlpSession:
    """Manages OTLP trace/metric export with high instance.id cardinality."""

    def __init__(self) -> None:
        headers = config.build_otlp_headers()
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "delta"
        )

        traces_endpoint = config.resolve_traces_endpoint()
        metrics_endpoint = config.resolve_metrics_endpoint()
        logger.info(
            "OTLP traces endpoint=%s headers=%s services=%s instances/service=%s",
            traces_endpoint,
            {
                k: ("***" if k.lower() in ("authorization", "api-key") else v)
                for k, v in headers.items()
            },
            len(config.SERVICES),
            catalog.ENTITY_COUNT,
        )

        self._span_exporter = OTLPSpanExporter(
            endpoint=traces_endpoint,
            headers=headers,
            timeout=30,
        )
        self._shared = _SharedSpanExporter(self._span_exporter)
        self._metric_exporter: OTLPMetricExporter | None = None
        if not config.OTLP_DISABLE_METRICS:
            self._metric_exporter = OTLPMetricExporter(
                endpoint=metrics_endpoint,
                headers=headers,
            )

        if config.is_ctrlb_backend():
            self._schedule_delay_millis = 2000
            self._max_export_batch_size = 64
        else:
            self._schedule_delay_millis = 500
            self._max_export_batch_size = 512

        # Lazy: (service_name, instance_id) → Tracer. Shared exporter avoids 502s.
        self._tracer_providers: list[TracerProvider] = []
        self._tracers: dict[tuple[str, str], Tracer] = {}

        default_resource = Resource.create(
            {
                "service.name": catalog.PRIMARY_SERVICE,
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

    def _make_resource(self, service_name: str, instance_id: str) -> Resource:
        meta = catalog.SERVICE_META.get(service_name, {})
        host_base = str(meta.get("host.name", f"{service_name}-1"))
        # Derive a plausible host per instance without exploding uniqueness too far
        suffix = instance_id.rsplit("-i", 1)[-1]
        try:
            n = int(suffix)
            host = f"ip-10-{(n // 256) % 32}-{(n // 16) % 16}-{n % 250 + 1}"
        except ValueError:
            host = host_base
        return Resource.create(
            {
                "service.name": service_name,
                "service.version": str(meta.get("version", "1.0.0")),
                "service.instance.id": instance_id,
                "deployment.environment": config.DEPLOYMENT_ENV,
                "host.name": host,
                "host.arch": "amd64",
                "os.type": "linux",
                "os.description": "Ubuntu 22.04.4 LTS",
                "os.version": "5.15.0-105-generic",
                "process.pid": int(meta.get("process.pid", 15000)) + (hash(instance_id) % 500),
                "process.runtime.name": "cpython",
                "process.runtime.version": "3.10.12",
                "process.runtime.description": "CPython 3.10.12",
                "process.command_line": f"gunicorn {service_name}.wsgi:app",
                "process.executable.path": "/usr/local/bin/python3.10",
                "container.id": f"{meta.get('container.id', service_name)}-{suffix}",
                "cloud.region": random.choice(("us-east-1", "eu-west-1", "ap-south-1")),
                "telemetry.distro.name": "opentelemetry",
                "telemetry.distro.version": "1.27.0",
                "telemetry.auto.version": "0.48b0",
            }
        )

    def tracer(self, service_name: str, instance_id: str | None = None) -> Tracer:
        instance_id = instance_id or catalog.pick_instance_id(service_name)
        key = (service_name, instance_id)
        existing = self._tracers.get(key)
        if existing is not None:
            return existing

        provider = TracerProvider(resource=self._make_resource(service_name, instance_id))
        provider.add_span_processor(
            BatchSpanProcessor(
                self._shared,
                schedule_delay_millis=self._schedule_delay_millis,
                max_export_batch_size=self._max_export_batch_size,
            )
        )
        self._tracer_providers.append(provider)
        tracer = provider.get_tracer("nr-fake-apm")
        self._tracers[key] = tracer
        return tracer

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
        self._span_exporter.shutdown()
        if self._metric_exporter is not None:
            self._metric_exporter.shutdown()
