"""Celery + OpenTelemetry (fork-safe) demo for CtrlB.

Start worker:
  ./run-celery-worker.sh

Enqueue:
  ./enqueue-celery.py
"""
import os

from celery import Celery
from celery.signals import worker_process_init

SERVICE_NAME_VALUE = "celery-fixed-test"


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            line = line.removeprefix("export ")
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip("'\"")
            # Always take values from .env for this demo (ignore stale shell exports)
            os.environ[key] = val


def configure_otel_env():
    load_env()
    host = os.environ.get("INGESTION_HOST")
    stream = os.environ.get("STREAM_NAME")
    token = os.environ.get("API_TOKEN")
    if not (host and stream and token):
        raise RuntimeError("Set INGESTION_HOST, STREAM_NAME, API_TOKEN in .env")

    # Force these — do NOT use setdefault (stale shell OTEL_* breaks CtrlB filters)
    os.environ["OTEL_EXPORTER"] = "otlp"
    os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    os.environ["OTEL_TRACES_EXPORTER"] = "otlp"
    os.environ["OTEL_METRICS_EXPORTER"] = "none"
    os.environ["OTEL_LOGS_EXPORTER"] = "none"
    os.environ["OTEL_SERVICE_NAME"] = SERVICE_NAME_VALUE
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"https://{host}/api/default"
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = (
        f"Authorization=Basic {token},stream-name={stream}"
    )


configure_otel_env()

app = Celery(
    "otel_demo",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1"),
)


@worker_process_init.connect(weak=False)
def init_celery_tracing(*args, **kwargs):
    # Imports MUST stay inside this handler (after fork).
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    configure_otel_env()  # re-apply in worker so headers/service are correct

    resource = Resource.create({SERVICE_NAME: SERVICE_NAME_VALUE})
    provider = TracerProvider(resource=resource)
    # Console: proves spans exist in worker log
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    # OTLP: immediate send to CtrlB (Simple = easier to debug than Batch)
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    CeleryInstrumentor().instrument()

    print(
        "[otel] worker tracing ready\n"
        f"  service = {SERVICE_NAME_VALUE}\n"
        f"  stream  = {os.environ.get('STREAM_NAME')}\n"
        f"  endpoint= {os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')}\n"
        f"  headers = {os.environ.get('OTEL_EXPORTER_OTLP_HEADERS')}",
        flush=True,
    )


@app.task(name="demo.work")
def work_task(n=3):
    total = sum(range(n))
    subtask.delay(total)
    return total


@app.task(name="demo.subtask")
def subtask(value):
    return value * 2
