# python_instrumentation_test

Minimal HTTP app for **zero-code** OpenTelemetry auto-instrumentation → CtrlB.

`app.py` has **no** OpenTelemetry imports. Tracing is applied by:

```bash
opentelemetry-instrument python3 app.py
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
opentelemetry-bootstrap -a install
cp .env.example .env   # set INGESTION_HOST, STREAM_NAME, API_TOKEN
```

## Run

```bash
./run.sh
```

Equivalent to:

```bash
OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_SERVICE_NAME=<STREAM_NAME> \
OTEL_EXPORTER_OTLP_ENDPOINT=https://<INGESTION_HOST>/api/default \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <API_TOKEN>,stream-name=<STREAM_NAME>" \
opentelemetry-instrument python3 app.py
```

## Endpoints

```bash
curl http://localhost:8080/health
curl http://localhost:8080/roll
curl http://localhost:8080/work
```

## Note

stdlib `http.server` has limited auto HTTP spans. For rich zero-code web traces
(Flask/Django instrumentors), use `flask_instrumentation_test` or
`django_instrumentation_test` with the same `opentelemetry-instrument` pattern.
