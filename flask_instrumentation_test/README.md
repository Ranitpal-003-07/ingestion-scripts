# flask_instrumentation_test

Flask app matching the **CtrlB Flask zero-code guide**.

`app.py` has **no** OpenTelemetry imports.

## Setup

```bash
cd flask_instrumentation_test
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
OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_SERVICE_NAME=flask_instrumentation_test \
OTEL_EXPORTER_OTLP_ENDPOINT=https://staging.ctrlb.dev/engine/api/default \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://staging.ctrlb.dev/engine/api/default/flask_instrumentation_test/_otel/v1/logs \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic YOUR_TOKEN,stream-name=flask_instrumentation_test" \
opentelemetry-instrument flask run -p 8080 --no-reload
```

## Traffic

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/roll
curl http://127.0.0.1:8080/work
# or: ./hit-endpoints.sh
```

## Gunicorn (deployment pattern)

Fork-safe: init OTEL in `gunicorn.conf.py` `post_fork`, **no `--preload`**, do **not** wrap with `opentelemetry-instrument`.

```bash
pip install gunicorn
# if port 8080 busy: PORT=8082 ./run-gunicorn.sh
./run-gunicorn.sh
```

### Gunicorn + gevent

Monkey-patch **before** OTEL in `gunicorn_gevent.conf.py`. HTTP exporter only. No `opentelemetry-instrument`.

```bash
pip install gunicorn gevent
./run-gunicorn-gevent.sh
./hit-endpoints.sh
```

| Do | Don't |
|----|--------|
| `gunicorn -c gunicorn_gevent.conf.py app:app` | `--preload` |
| `gevent.monkey.patch_all()` first in `post_fork` | `opentelemetry-instrument gunicorn …` |
| OTLP `http/protobuf` | gRPC exporter with gevent |

```bash
BASE_URL=http://127.0.0.1:8080 ./hit-endpoints.sh
```

CtrlB: service = your `STREAM_NAME` (same as `./run.sh`).

## Docker

```bash
./run-docker.sh
# or PORT=8082 ./run-docker.sh
```

Same as the guide:

```bash
docker build -t flask-otel-test .

docker run --rm -p 8080:8080 \
  -e OTEL_EXPORTER=otlp \
  -e OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
  -e OTEL_SERVICE_NAME=flask_instrumentation_test \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=https://staging.ctrlb.dev/engine/api/default \
  -e OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://staging.ctrlb.dev/engine/api/default/flask_instrumentation_test/_otel/v1/logs \
  -e OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic YOUR_TOKEN,stream-name=flask_instrumentation_test" \
  flask-otel-test
```

Image `CMD`: `opentelemetry-instrument python app.py`
