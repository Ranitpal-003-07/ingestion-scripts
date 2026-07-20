# ingest_nr_logs.py

## Overview

Ingests synthetic WAF nested logs into **New Relic** via the [Log API](https://docs.newrelic.com/docs/logs/log-api/introduction-log-api/). Payload generation reuses `generate_waf_match()` from [`ingest_logs.py`](ingest_logs.py); each record is wrapped as a New Relic log event with `service.name`, `deployment.environment`, and a nested `waf` attribute.

## Endpoint

| Property | Value |
|----------|-------|
| **URL (US default)** | `https://log-api.newrelic.com/log/v1` |
| **URL (EU)** | `https://log-api.eu.newrelic.com/log/v1` |
| **Method** | `POST` |
| **Payload** | JSON array of log events (one batch per second, size = configured logs/sec) |
| **Timeout** | 10 seconds per request |

Set the URL with the `LOG_API_ENDPOINT` environment variable (trailing slashes are stripped). See [`ingest_nr_logs.py`](ingest_nr_logs.py).

## Authentication / headers

| Header | Value |
|--------|-------|
| `Api-Key` | Your New Relic **ingest** license key (`NEW_RELIC_LICENSE_KEY`) |
| `Content-Type` | `application/json` |

The license key is validated at startup by [`nr_traces/config.py`](nr_traces/config.py) (`validate_config()`).

## Configuration

### Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `NEW_RELIC_LICENSE_KEY` | **Yes** | — | Ingest license key (e.g. `NRAK-...`) |
| `LOGS_PER_SECOND` | No | `30` | Events per batch per second (max **200**) |
| `LOG_API_ENDPOINT` | No | `https://log-api.newrelic.com/log/v1` | Log API URL (use EU URL for EU accounts) |
| `NR_LOG_SERVICE` | No | `demo-waf-ingest` | `service.name` on each event |
| `DEPLOYMENT_ENV` | No | `demo` | `deployment.environment` on each event |

**Rate resolution order:** `--rate` CLI flag → `LOGS_PER_SECOND` env → default `30`. Values above 200 are capped with a warning.

### Example

```bash
export NEW_RELIC_LICENSE_KEY="NRAK-xxxxxxxx"
export LOGS_PER_SECOND=50
export DEPLOYMENT_ENV=staging
export NR_LOG_SERVICE=demo-waf-ingest
# Optional EU:
# export LOG_API_ENDPOINT="https://log-api.eu.newrelic.com/log/v1"
```

## Setup

1. **Python:** 3.10+ recommended (`int | None` type hints in this script).
2. **Virtualenv (optional):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Dependencies** from repo root:
   ```bash
   pip install -r requirements.txt
   pip install requests
   ```
   OpenTelemetry packages in `requirements.txt` satisfy shared `nr_traces` config; `requests` is used for the Log API POST.

## How to run

1. Complete Setup and export `NEW_RELIC_LICENSE_KEY`.
2. **Smoke test** (one batch, then exit):
   ```bash
   python ingest_nr_logs.py --once -v
   ```
3. **Continuous ingestion** (default 30 logs/sec):
   ```bash
   python ingest_nr_logs.py
   ```
4. **Override rate:**
   ```bash
   python ingest_nr_logs.py --rate 50
   ```
5. Stop continuous mode with **Ctrl+C** or **SIGTERM** (graceful shutdown flag).

Successful batches return HTTP **200** or **202**. Progress is logged every 10 seconds.

## CLI flags

| Flag | Description |
|------|-------------|
| `--once` | Send one batch and exit (smoke test) |
| `--rate N` | Logs per second; overrides `LOGS_PER_SECOND` env (default 30, max 200) |
| `-v`, `--verbose` | Enable debug logging |

```bash
python ingest_nr_logs.py --help
```

## Verification

Allow **2–5 minutes** for data to appear in New Relic Logs or NRQL.

```sql
SELECT count(*) FROM Log
WHERE service.name = 'demo-waf-ingest' SINCE 30 minutes ago
```

```sql
SELECT count(*) FROM Log
WHERE waf.action = 'BLOCK' SINCE 30 minutes ago
```

Adjust `service.name` if you changed `NR_LOG_SERVICE`. Use `-v` and check for `Successfully sent N log events` at debug level or interval info logs in continuous mode.

## Related scripts

- [`ingest_logs.md`](ingest_logs.md) — same WAF payload generator, sent to CtrlB staging instead of New Relic.
- [`ingest_traces.md`](ingest_traces.md) — synthetic OpenTelemetry traces/metrics to New Relic OTLP (shared `nr_traces` config).
