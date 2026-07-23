# go_instrumentation_test

Go HTTP app matching the **CtrlB Go traces guide** (no zero-code agent).

- `otel.go` — `initTracer` (OTLP HTTP)
- `main.go` — `otelhttp.NewHandler` + demo endpoints
- Traces only (no metrics/logs SDK)

## Prerequisites

- Go 1.21+
- CtrlB OTLP credentials in `.env`

## Step 1 — Install dependencies

```bash
cd go_instrumentation_test

go get go.opentelemetry.io/otel \
  go.opentelemetry.io/otel/sdk/trace \
  go.opentelemetry.io/otel/sdk/resource \
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp \
  go.opentelemetry.io/otel/propagation \
  go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp

go mod tidy
```

## Step 2 — Configure `.env`

```bash
cp .env.example .env
```

```bash
INGESTION_HOST=staging.ctrlb.dev/engine
STREAM_NAME=go_instrumentation_test
API_TOKEN=your_token
```

## Step 3 — Run (CtrlB exporter env)

```bash
./run.sh
```

Same as the guide:

```bash
OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_SERVICE_NAME=go_instrumentation_test \
OTEL_EXPORTER_OTLP_ENDPOINT=https://staging.ctrlb.dev/engine/api/default \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://staging.ctrlb.dev/engine/api/default/go_instrumentation_test/_otel/v1/logs \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic YOUR_TOKEN,stream-name=go_instrumentation_test" \
go run .
```

## Step 4 — Generate traffic

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/roll
curl http://127.0.0.1:8080/work
# or: ./hit-endpoints.sh
```

## CtrlB

Traces explorer → stream **`go_instrumentation_test`** → HTTP server spans + `dice.roll` / `work.*`.
