import os

bind = "0.0.0.0:8080"
workers = 2
worker_class = "uvicorn.workers.UvicornWorker"
# do NOT set preload_app = True

def post_fork(server, worker):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.instrumentation.django import DjangoInstrumentor

    resource = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "asgi-gunicorn-uvicorn"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    if not DjangoInstrumentor().is_instrumented_by_opentelemetry:
        DjangoInstrumentor().instrument()

def worker_exit(server, worker):
    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()