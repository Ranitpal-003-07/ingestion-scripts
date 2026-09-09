# ingest_traces.py

## Overview

Ingests **synthetic OpenTelemetry traces** via OTLP/HTTP for APM query testing.
Defaults to New Relic; targets **CtrlB** with `STREAM_NAME` (no auth required).

Spans are shaped for the CtrlB prod schema (underscore columns): dual HTTP/DB
semconv attrs (`http_response_status_code` + `http_status_code`,
`db_system_name` + `db_system`, `db_sql_table` / `db_mongodb_collection` /
`db_namespace`), NR-default errors (5xx + exceptions, separate 4xx scenario),
and SERVER/CLIENT kinds for transaction vs DB queries.

## Endpoint

| Backend | Traces URL |
|---------|------------|
| New Relic | `{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces` (default `https://otlp.nr-data.net`) |
| CtrlB | `{base}/v1/traces` + `stream-name: {STREAM_NAME}` header |

Do **not** use the logs-style `/{stream}/_otel/v1/traces` path for spans — that 404s.

## CtrlB example

```bash
cd random
cp .env.traces.example .env   # set STREAM_NAME
set -a && source .env && set +a
pip install -r requirements.txt
python ingest_traces.py --once
python ingest_traces.py --rate 5
```

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://staging.ctrlb.dev/engine/api/default"
export STREAM_NAME="your_traces_stream"
python ingest_traces.py --rate 5
```

Metrics are **disabled by default** on CtrlB (`OTLP_DISABLE_METRICS`).

## What gets emitted (query coverage)

| Scenario | Why |
|----------|-----|
| `checkout_happy_path` | SERVER txn + postgres CLIENT (`db_sql_table=orders`) + HTTP client |
| `checkout_payment_failure` | 5xx + `status_code=ERROR` + exception |
| `checkout_client_error` | 4xx only (should **not** count as NR-default error) |
| `auth_slow_trace` | Slow SERVER + redis CLIENT (apdex / slowest) |
| `search_mixed_db` | mysql / mongodb / redis normalized DB keys |
| `db_error_query` | DB error + `db_response_status_code=500` |
| `grpc_inventory_check` | `rpc_system` / `rpc_method` / `rpc_grpc_status_code` |
| `kafka_order_fulfilled` | messaging CONSUMER/PRODUCER |

Demo `service.name` values: `demo-api-gateway`, `demo-orders-service`,
`demo-inventory-service`, `demo-payment-service`, `demo-notification-worker`,
`demo-auth-service`.

## CtrlB verification SQL

```sql
SELECT span_kind, COUNT(*) FROM "<stream>" GROUP BY span_kind ORDER BY 2 DESC;
SELECT span_status, COUNT(*) FROM "<stream>" GROUP BY span_status;

SELECT service_name, operation_name, COUNT(*) FROM "<stream>"
WHERE service_name LIKE 'demo-%'
  AND (span_kind = '2' OR span_kind = 'SPAN_KIND_SERVER')
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20;

SELECT COALESCE(NULLIF(db_system_name,''), db_system) AS sys,
       COALESCE(NULLIF(db_operation_name,''), db_operation) AS op,
       COALESCE(NULLIF(db_sql_table,''), NULLIF(db_mongodb_collection,''),
                NULLIF(db_namespace,''), db_name) AS target,
       COUNT(*) FROM "<stream>"
WHERE (span_kind = '3' OR span_kind = 'SPAN_KIND_CLIENT')
  AND COALESCE(NULLIF(db_system_name,''), db_system, '') != ''
GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 20;
```

## Package layout

| Module | Role |
|--------|------|
| [`nr_traces/attrs.py`](../nr_traces/attrs.py) | Schema-aligned attribute builders |
| [`nr_traces/scenarios.py`](../nr_traces/scenarios.py) | Weighted APM scenarios |
| [`nr_traces/config.py`](../nr_traces/config.py) | Endpoint / stream / auth |
| [`nr_traces/otlp.py`](../nr_traces/otlp.py) | OTLP session |
