# OpenObserve correlation ingest

Synthetic **logs** (JSON), **traces** (OTLP), and **metrics** (OTLP) for testing the
correlation engine on [OpenObserve Cloud](https://cloud.openobserve.ai).

Data uses **different field names per signal** for the same workload (e.g. logs `app` /
`namespace`, traces `service.name` / `k8s.namespace.name`, metrics `service` /
`namespace`).

## Workloads

| ID | Identity | Service | Notes |
|----|----------|---------|--------|
| k8s-checkout | K8s cluster + namespace | checkout | Some errors / high CPU |
| k8s-cart | K8s cluster + namespace | cart | Healthy path |
| aws-checkout | AWS account + region | checkout | Same name as K8s checkout, different identity set |

## Setup

```bash
cd /Users/mac/Desktop/ingestion-scripts/o2_correlation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with values from Cloud **Data Sources** (cURL):

- `O2_ORG` — organization id in the URL
- `O2_USER` / `O2_PASSWORD` — Basic auth (email + password or ingest token)

### Multiple streams

Set comma-separated lists to **fan out** the same correlation demo data to every stream
(useful when logs, traces, and metrics live in different stream names):

```bash
O2_LOG_STREAMS=default,correlation_logs
O2_TRACE_STREAMS=default,correlation_traces
O2_METRICS_STREAMS=default,container_cpu
```

- **Logs**: one `POST` per stream (`/api/{org}/{stream}/_json`).
- **Traces / metrics**: OTLP to `/v1/traces` and `/v1/metrics` with the
  `stream-name` header per target (override header key via `O2_STREAM_HEADER_KEY`).

Legacy single-stream env vars still work: `O2_LOG_STREAM`, `O2_TRACE_STREAM`,
`O2_METRICS_STREAM` (used when the matching `*_STREAMS` list is unset).

## Run

```bash
# Continuous ingest until Ctrl-C (recommended)
./run.sh

# One batch then exit
./run.sh --once

# Or via python (after venv + pip install)
python ingest_all.py
python ingest_all.py --once --logs-only
```

Open the **AP1** UI: https://ap1.openobserve.ai (not `cloud.openobserve.ai`).

## Verify in Cloud

1. **Logs** → each stream in `O2_LOG_STREAMS` → search `app=checkout` or `level=error`
2. **Traces** → each stream in `O2_TRACE_STREAMS` → find `checkout` / span `POST /pay`
3. **Metrics** → each stream in `O2_METRICS_STREAMS` → `container_cpu` with labels
   `service`, `namespace`, `cluster`

## Test correlation in the UI

1. **Settings → Correlation → Field aliases** — ensure groups cover:
   - service: `app`, `service`, `service.name`, `service_name`
   - k8s-namespace: `namespace`, `k8s.namespace.name`
   - k8s-cluster: `cluster`, `k8s.cluster.name`
   - aws-account / aws-region if testing multi-set identity
2. **Service discovery** — identity sets e.g. K8s `k8s-cluster` + `k8s-namespace`, AWS
   `aws-account` + `aws-region`
3. Wait for **Discovered services** after ingest
4. Open a **k8s-checkout** log → **Correlate** → related traces/metrics for K8s only
   (not the AWS `checkout` twin)

## Endpoints (for reference)

| Signal | Method | Path / routing |
|--------|--------|----------------|
| Logs | POST | `{O2_BASE_URL}/api/{O2_ORG}/{stream}/_json` (per `O2_LOG_STREAMS`) |
| Traces | POST OTLP | `{O2_BASE_URL}/api/{O2_ORG}/v1/traces` + `stream-name` header |
| Metrics | POST OTLP | `{O2_BASE_URL}/api/{O2_ORG}/v1/metrics` + `stream-name` header |

Default `O2_BASE_URL` in `.env.example` is the **AP1** host when your Data Sources cURL
looks like `https://ap1-api.openobserve.ai/api/{org}/...`. Use `https://api.openobserve.ai`
for the primary US Cloud region.

## Related docs

OpenObserve repo: `src/config/src/meta/correlation/` and `00-how-it-makes-life-easier.md`
