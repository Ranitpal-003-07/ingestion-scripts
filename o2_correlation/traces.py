"""OTLP/HTTP trace export for correlation demo workloads."""

from __future__ import annotations

import logging
import random

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from o2_correlation import config, scenarios

logger = logging.getLogger(__name__)


class _SharedSpanExporter:
    """One exporter shared by many processors; only we call real shutdown()."""

    def __init__(self, exporter: OTLPSpanExporter) -> None:
        self._exporter = exporter

    def export(self, spans):  # noqa: ANN001
        return self._exporter.export(spans)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis=timeout_millis)

    def shutdown(self) -> None:
        return None


class _StreamTraceBackend:
    """One OTLP trace exporter + tracers per OpenObserve stream."""

    def __init__(self, stream_name: str) -> None:
        self.stream_name = stream_name
        endpoint = config.traces_otlp_url()
        headers = config.build_otlp_headers(stream_name)
        self._raw_exporter = OTLPSpanExporter(
            endpoint=endpoint, headers=headers, timeout=30
        )
        self._shared = _SharedSpanExporter(self._raw_exporter)
        self._providers: list[TracerProvider] = []
        self._tracers: dict[str, trace.Tracer] = {}

    def _tracer_for(self, workload: scenarios.Workload) -> trace.Tracer:
        existing = self._tracers.get(workload.workload_id)
        if existing is not None:
            return existing
        resource = Resource.create(scenarios.build_trace_resource_attributes(workload))
        provider = TracerProvider(resource=resource)
        # SimpleSpanProcessor exports immediately — no batch flush races.
        provider.add_span_processor(SimpleSpanProcessor(self._shared))
        self._providers.append(provider)
        tracer = provider.get_tracer("o2-correlation-demo")
        self._tracers[workload.workload_id] = tracer
        return tracer

    def emit_workload(self, workload: scenarios.Workload) -> str:
        tracer = self._tracer_for(workload)
        span_name = scenarios.build_trace_span_name(workload)
        failed = scenarios.trace_should_fail(workload)

        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("http.method", "POST" if "POST" in span_name else "GET")
            span.set_attribute("http.route", span_name.split(" ", 1)[-1])
            for key, value in scenarios.build_trace_span_attributes(workload).items():
                span.set_attribute(key, value)
            if failed:
                span.set_attribute("http.status_code", 500)
                span.set_status(trace.Status(trace.StatusCode.ERROR, "gateway timeout"))
            else:
                span.set_attribute("http.status_code", 200)
            return format(span.get_span_context().trace_id, "032x")

    def flush(self) -> None:
        for provider in self._providers:
            provider.force_flush()

    def shutdown(self) -> None:
        self.flush()
        for provider in self._providers:
            provider.shutdown()
        self._raw_exporter.shutdown()


class TraceSession:
    """Fan-out the same spans to every configured trace stream."""

    def __init__(self, stream_names: list[str] | None = None) -> None:
        names = stream_names if stream_names is not None else config.O2_TRACE_STREAMS
        self._backends = [_StreamTraceBackend(name) for name in names]

    def emit_all(self) -> list[str]:
        ids: list[str] = []
        for workload in scenarios.active_workloads():
            for backend in self._backends:
                trace_id = backend.emit_workload(workload)
                ids.append(trace_id)
                logger.debug(
                    "Emitted trace stream=%s workload=%s trace_id=%s",
                    backend.stream_name,
                    workload.workload_id,
                    trace_id,
                )
        return ids

    def flush(self) -> None:
        for backend in self._backends:
            backend.flush()

    def shutdown(self) -> None:
        for backend in self._backends:
            backend.shutdown()
