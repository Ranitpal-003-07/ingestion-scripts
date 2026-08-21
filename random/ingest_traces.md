# ingest_traces.py

## Overview

Ingests **synthetic OpenTelemetry traces and metrics** via OTLP/HTTP. Defaults to New Relic, but can target CtrlB/custom OTLP collectors by changing endpoint/auth env vars. The [`nr_traces`](nr_traces/) package emits weighted random APM scenarios (checkout, errors, database calls, etc.) across six `demo-*` services. Supports continuous load or a single-trace smoke test.

## Endpoint

Base URL from `OTEL_EXPORTER_OTLP_ENDPOINT` (default US OTLP). Exporters append standard paths in [`nr_traces/otlp.py`](nr_traces/otlp.py):

| Property | Value |
|----------|-------|
| **Traces URL** | `{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces` |
| **Metrics URL** | `{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/metrics` |
| **Default base** | `https://otlp.nr-data.net` |
| **Method** | `POST` (OTLP/protobuf over HTTP) |
| **Payload** | OpenTelemetry trace spans and metrics (batched by SDK exporters) |

Example resolved URLs with defaults:

- `https://otlp.nr-data.net/v1/traces`
- `https://otlp.nr-data.net/v1/metrics`

## Authentication / headers

OTLP exporters send one auth header:

| Header | Value |
|--------|-------|
| `OTLP_AUTH_HEADER` (default `api-key`) | `OTLP_AUTH_TOKEN` (or fallback `NEW_RELIC_LICENSE_KEY`) |

Validated at startup via [`nr_traces/config.py`](nr_traces/config.py) `validate_config()`.

## Configuration

### Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `NEW_RELIC_LICENSE_KEY` | Conditional | — | New Relic ingest key (fallback auth token) |
| `OTLP_AUTH_TOKEN` | Conditional | `NEW_RELIC_LICENSE_KEY` | Auth token for CtrlB/custom OTLP |
| `OTLP_AUTH_HEADER` | No | `api-key` | Auth header name for OTLP requests |
| `TRACES_PER_SECOND` | No | `5` | Traces emitted per loop iteration (max **100**) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | `https://otlp.nr-data.net` | OTLP base URL (no trailing path) |
| `DEPLOYMENT_ENV` | No | `demo` | `deployment.environment` resource attribute |
| `SERVICE_INSTANCE_ID` | No | Random UUID | `service.instance.id` on all demo services |

**Rate resolution order:** `--rate` CLI flag → `TRACES_PER_SECOND` env → default `5`. Values above 100 are capped with a warning.

### Demo services (resource `service.name`)

Defined in [`nr_traces/config.py`](nr_traces/config.py):

- `demo-api-gateway`
- `demo-orders-service`
- `demo-inventory-service`
- `demo-payment-service`
- `demo-notification-worker`
- `demo-auth-service`

Scenarios are implemented in [`nr_traces/scenarios.py`](nr_traces/scenarios.py).

### Example

```bash
export NEW_RELIC_LICENSE_KEY="NRAK-xxxxxxxx"
export TRACES_PER_SECOND=10
export DEPLOYMENT_ENV=demo
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp.nr-data.net"
```

### CtrlB OTLP example

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://<ctrlb-otlp-host>"
export OTLP_AUTH_HEADER="Authorization"
export OTLP_AUTH_TOKEN="Bearer <token>"
export TRACES_PER_SECOND=5
```

## Setup

1. **Python:** 3.10+ recommended.
2. **Virtualenv (optional):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Dependencies** from repo root:
   ```bash
   pip install -r requirements.txt
   ```
   Includes OpenTelemetry API/SDK and `opentelemetry-exporter-otlp-proto-http` (see [`requirements.txt`](requirements.txt)).

## How to run

1. Complete Setup and export auth envs (`NEW_RELIC_LICENSE_KEY` or `OTLP_AUTH_TOKEN`).
2. **Smoke test** (one trace, flush, exit):
   ```bash
   python ingest_traces.py --once
   ```
3. **Continuous ingestion** (default 5 traces/sec):
   ```bash
   python ingest_traces.py
   ```
4. **Override rate:**
   ```bash
   python ingest_traces.py --rate 10
   ```
5. **Verbose:**
   ```bash
   python ingest_traces.py -v
   ```
6. Stop with **Ctrl+C** or **SIGTERM** — exporters flush on shutdown.

Progress logs every 10 seconds in continuous mode.

## CLI flags

| Flag | Description |
|------|-------------|
| `--once` | Emit a single random trace, flush, and exit |
| `--rate N` | Traces per second; overrides `TRACES_PER_SECOND` env (default 5, max 100) |
| `-v`, `--verbose` | Enable debug logging (includes `trace.id` per emit) |

```bash
python ingest_traces.py --help
```

## Verification

Allow **2–5 minutes** before querying New Relic.

**NRQL examples** (from [`ingest_traces.py`](ingest_traces.py) docstring):

```sql
SELECT count(*) FROM Span
WHERE service.name LIKE 'demo-%' SINCE 30 minutes ago
```

```sql
SELECT count(*) FROM Span
WHERE service.name = 'demo-api-gateway' AND transaction.name IS NOT NULL
SINCE 30 minutes ago
```

```sql
SELECT count(*) FROM Span WHERE error.message IS NOT NULL SINCE 30 minutes ago
```

```sql
SELECT count(*) FROM Span WHERE db.system IS NOT NULL SINCE 30 minutes ago
```

**UI:** APM & Services → filter **demo-*** OpenTelemetry services → Transactions, Databases, External services, Distributed tracing, Service map.

**Stdout:** `--once` logs `Emitted trace trace.id=...`; continuous mode logs interval counts and errors.

## Related scripts

- [`ingest_nr_logs.md`](ingest_nr_logs.md) — WAF logs to New Relic Log API (same license key validation).
- [`ingest_logs.md`](ingest_logs.md) — CtrlB WAF log ingestion (no New Relic).

### `nr_traces` package

Not run directly; used by `ingest_traces.py`:

| Module | Role |
|--------|------|
| [`nr_traces/config.py`](nr_traces/config.py) | Env vars, license key validation, service list |
| [`nr_traces/otlp.py`](nr_traces/otlp.py) | `OtlpSession` — OTLP trace/metric exporters |
| [`nr_traces/scenarios.py`](nr_traces/scenarios.py) | Synthetic trace scenarios |
| [`nr_traces/ids.py`](nr_traces/ids.py) | Trace/customer/order ID helpers |
