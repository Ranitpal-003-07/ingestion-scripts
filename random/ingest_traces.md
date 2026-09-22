# ingest_traces.py

## Overview

Ingests **synthetic OpenTelemetry traces** via OTLP/HTTP for APM query testing
(Transactions / Database / External tabs). Defaults to New Relic; targets
**CtrlB** with `STREAM_NAME` (no auth required).

Catalog size (`nr_traces/catalog.py`): **520** transaction routes, external
peers, DB operations, and instance IDs per service — enough for pagination
(LIMIT 100), ranks (top 3), and high-cardinality instance filters.

## Endpoint

| Backend | Traces URL |
|---------|------------|
| New Relic | `{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces` (default `https://otlp.nr-data.net`) |
| CtrlB | `{base}/v1/traces` + `stream-name: {STREAM_NAME}` header |

Do **not** use the logs-style `/{stream}/_otel/v1/traces` path for spans — that 404s.

## CtrlB example

```bash
cd random
export OTEL_EXPORTER_OTLP_ENDPOINT="https://staging.ctrlb.dev/engine/api/default"
export STREAM_NAME="traces_testing_sep"
python3 ingest_traces.py --rate 30 --spread 45
```

`--spread 45` backdates span timestamps across the last 45 minutes so stats
charts have buckets. Metrics are **disabled by default** on CtrlB.

## What gets emitted

| Service | Role |
|---------|------|
| `demo-checkout` | Busy primary — External tab end-to-end |
| `demo-api-gateway` / orders / auth / … | Multi-service Overview |
| `demo-edge-bff` | Outbound **without** `db_system` (External-only / soft-fail) |
| `demo-static-cdn` | SERVER + INTERNAL only → **empty External** |

### External protocols (entity_type coverage)

Fixed mix for External client spans:

| entity_type | % | Recipe peer / fields |
|-------------|---|----------------------|
| `http` | 40 | `payments` + `http_method=GET`, `http_route=/charge` |
| `grpc` | 25 | `inventory` / `payments` + `rpc_system=grpc` (no HTTP fields) |
| `kafka` | 15 | `orders-bus` + `messaging_system=kafka` |
| `graphql_http` | 10 | `catalog-graphql` + HTTP + `graphql.operation.*` |
| `other` | 10 | `mystery-peer` (peer_service only) |

Dual-type: `payments` as **http** and **grpc** (table two rows). Database spans still set `db_system` and are excluded from External. Kafka/messaging use `span_kind=CLIENT` (3).


### Database vs External

- DB clients: `span_kind=CLIENT`, **`db_system` set** (postgres/mysql/mongo/redis/es), often with `peer_service` too → **Database tab**
- Non-DB clients: **`db_system` empty** + `peer_service` / `net_peer_name` → **External only**

### Transactions / instances

- 520 SERVER `operation_name` routes
- 520 `service.instance.id` values per service (lazy TracerProviders)

## Package layout

| Module | Role |
|--------|------|
| [`nr_traces/catalog.py`](../nr_traces/catalog.py) | 520-entity catalogs + special peers |
| [`nr_traces/attrs.py`](../nr_traces/attrs.py) | Schema-aligned attribute builders |
| [`nr_traces/scenarios.py`](../nr_traces/scenarios.py) | Weighted scenarios + timed spans |
| [`nr_traces/config.py`](../nr_traces/config.py) | Endpoint / stream / spread |
| [`nr_traces/otlp.py`](../nr_traces/otlp.py) | Shared exporter + lazy instances |
