# ingest_metrics.py

## Overview

Ingests **synthetic Prometheus-style OTLP metrics** for PromQL alert testing against checkquery-engine-dev / Seekr metrics streams.

Supports controllable scenarios: **trigger**, **resolve**, **multiseries** (partial breach), threshold gauges, `rate()` counters, and `histogram_quantile()` latency alerts.

Does **not** modify checkquery-engine-dev — runs entirely from this repo.

## Endpoint

| Backend | Metrics URL |
|---------|-------------|
| CtrlB | `{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/metrics` + `stream-name: {STREAM_NAME}` header |
| New Relic | `{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/metrics` + `api-key` header |

Same routing pattern as traces: stream via header, not `/{stream}/_otel/...` path.

## Quick start

```bash
cd random
cp .env.metrics.example .env   # set STREAM_NAME
set -a && source .env && set +a
pip install -r requirements.txt
python ingest_metrics.py --once
python ingest_metrics.py --mode baseline
```

## Metric family

| Metric | Type | Labels |
|--------|------|--------|
| `demo_up` | gauge (0/1) | `service`, `instance`, `env`, `region` |
| `demo_cpu_usage_ratio` | gauge 0–1 | same |
| `demo_memory_usage_ratio` | gauge 0–1 | same |
| `demo_http_requests_total` | counter | same |
| `demo_http_errors_total` | counter | same |
| `demo_http_request_duration_seconds` | histogram | same |

**Series (6 instances, 3 services):**

| service | instances | region |
|---------|-----------|--------|
| demo-api | demo-api-1, demo-api-2 | us-east-1 |
| demo-orders | demo-orders-1, demo-orders-2 | eu-west-1 |
| demo-payments | demo-payments-1, demo-payments-2 | eu-west-1 / us-east-1 |

## Modes

| Mode | Effect |
|------|--------|
| `baseline` | Healthy: CPU ~0.25–0.4, low errors, low latency, `up=1` |
| `spike_cpu` | Targeted series CPU → ~0.95+ |
| `spike_errors` | Targeted series error rate ~40% (8 errors / 20 requests per tick) |
| `spike_latency` | Targeted series latency → 1.2–2.5s |
| `down` | Targeted series `demo_up=0`, no requests |
| `recover` | Same as `baseline` |

### Targeting (multiseries partial fire)

Only the matched series breach; others stay healthy:

```bash
# Fire CPU alert for demo-api only; demo-orders and demo-payments stay green
python ingest_metrics.py --mode spike_cpu --target service=demo-api

# Fire on a single instance
python ingest_metrics.py --mode down --target instance=demo-api-1
```

### Auto recover

```bash
# Spike errors for 2 minutes, then return to baseline
python ingest_metrics.py --mode spike_errors --target service=demo-payments --hold-seconds 120
```

## Example PromQL alert rules

Use these in checkquery-engine-dev against your metrics stream.

**CPU threshold (per service):**

```promql
avg by (service) (demo_cpu_usage_ratio) > 0.9
```

**Error rate** (counters are exported as **cumulative** so `rate()` works):

```promql
sum by (service) (rate(demo_http_errors_total[1m]))
/
clamp_min(sum by (service) (rate(demo_http_requests_total[1m])), 0.001)
> 0.05
```

If `rate()` is empty, confirm counters exist first: `demo_http_requests_total` and `demo_http_errors_total`. Restart ingest after any temporality change — old delta data will not work with `rate()`.

**Latency p99:**

```promql
histogram_quantile(
  0.99,
  sum by (le, service) (rate(demo_http_request_duration_seconds_bucket[5m]))
) > 1
```

**Instance down:**

```promql
demo_up == 0
```

**Multiseries — only demo-api should breach when targeted:**

```promql
max by (service) (demo_cpu_usage_ratio) > 0.9
```

## Test plan (fire → resolve)

1. **Baseline** — run `python ingest_metrics.py --mode baseline`; confirm all series healthy in metrics explorer.
2. **Fire CPU** — `python ingest_metrics.py --mode spike_cpu --target service=demo-api`; alert should fire for `demo-api` only.
3. **Resolve** — Ctrl+C, then `python ingest_metrics.py --mode baseline` (or `--mode recover`); alert resolves after evaluation window.
4. **Fire errors** — `--mode spike_errors --target service=demo-payments`.
5. **Fire latency** — `--mode spike_latency --target instance=demo-orders-1`.
6. **Fire down** — `--mode down --target instance=demo-api-2`.
7. **Auto recover** — `--mode spike_cpu --hold-seconds 60` and wait; values return to baseline without manual switch.

## Package layout

| Module | Role |
|--------|------|
| [`nr_metrics/config.py`](../nr_metrics/config.py) | Endpoint / stream / headers |
| [`nr_metrics/otlp.py`](../nr_metrics/otlp.py) | OTLP metric exporter + instruments |
| [`nr_metrics/scenarios.py`](../nr_metrics/scenarios.py) | Modes, targets, per-series values |
