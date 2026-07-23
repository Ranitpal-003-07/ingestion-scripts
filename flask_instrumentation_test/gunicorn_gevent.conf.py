# Gunicorn + gevent + OpenTelemetry (CtrlB deployment pattern).
#
# Rules:
# - do NOT set preload_app = True
# - do NOT use opentelemetry-instrument with this conf
# - monkey-patch gevent BEFORE any opentelemetry imports
# - use OTLP HTTP (http/protobuf), not gRPC

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "gevent"
# preload_app = False


def post_fork(server, worker):
    # 1) patch BEFORE any opentelemetry import in this worker
    import gevent.monkey

    gevent.monkey.patch_all()

    import logging

    # 2) init OTEL after patch (HTTP exporter)
    from opentelemetry import trace
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service = os.getenv("OTEL_SERVICE_NAME", "flask_instrumentation_test")
    resource = Resource.create({SERVICE_NAME: service})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)

    otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, LoggingHandler) for h in root.handlers):
        root.addHandler(otel_handler)

    LoggingInstrumentor().instrument(set_logging_format=True)

    import app as flask_app

    logging.getLogger("flask_instrumentation_test").setLevel(logging.INFO)
    FlaskInstrumentor().instrument_app(flask_app.app)

    server.log.info(
        "otel gevent post_fork ready worker=%s service=%s traces+logs",
        worker.pid,
        service,
    )


def worker_exit(server, worker):
    from opentelemetry import trace
    from opentelemetry._logs import get_logger_provider

    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()

    lp = get_logger_provider()
    if hasattr(lp, "shutdown"):
        lp.shutdown()
