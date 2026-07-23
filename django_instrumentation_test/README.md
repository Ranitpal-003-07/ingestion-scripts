# django_instrumentation_test

Django app matching the **CtrlB Django zero-code guide**.

Views have **no** OpenTelemetry imports. The CLI patches Django at startup:

```bash
opentelemetry-instrument python manage.py runserver --noreload
```

Settings module: **`config.settings`** (docs often say `myproject.settings`).

## Setup

```bash
cd django_instrumentation_test
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

Same as the guide:

```bash
DJANGO_SETTINGS_MODULE=config.settings \
OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_SERVICE_NAME=django_instrumentation_test \
OTEL_EXPORTER_OTLP_ENDPOINT=https://staging.ctrlb.dev/engine/api/default \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://staging.ctrlb.dev/engine/api/default/django_instrumentation_test/_otel/v1/logs \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic YOUR_TOKEN,stream-name=django_instrumentation_test" \
opentelemetry-instrument python manage.py runserver --noreload
```

## Traffic

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/roll
curl http://127.0.0.1:8080/work
# or: ./hit-endpoints.sh
# COUNT=20 ./hit-endpoints.sh
```

## CtrlB

Stream: **`django_instrumentation_test`** — automatic Django HTTP spans.
