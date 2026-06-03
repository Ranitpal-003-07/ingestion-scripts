# ingest_logs.py

## Overview

Continuously generates synthetic AWS WAF-style nested JSON records and POSTs them in batches to a CtrlB staging ingest endpoint. Payloads include nested `httprequest`, rule groups, rate rules, and numeric fields for int/float type testing.

## Endpoint

| Property | Value |
|----------|-------|
| **URL** | `http://staging.ctrlb.dev:8080/api/default/object_table_bug/v3/_json_evolving` |
| **Method** | `POST` |
| **Payload** | JSON array of WAF match objects (batch size = `LOGS_PER_SECOND` per second) |
| **Timeout** | 5 seconds per request |

Change the URL by editing the `ENDPOINT` constant at the top of [`ingest_logs.py`](ingest_logs.py).

## Authentication / headers

No API key. The script sends:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `User-Agent` | `MetricsGenerator/1.0` |

Configure via the `HEADERS` dict in [`ingest_logs.py`](ingest_logs.py).

## Configuration

All settings are **constants in the script** (no environment variables or CLI).

| Constant | Default | Purpose |
|----------|---------|---------|
| `ENDPOINT` | CtrlB staging URL above | Ingest URL |
| `HEADERS` | See script | HTTP headers |
| `LOGS_PER_SECOND` | `100` | Records per batch; one batch per second |
| `WEBACL_ID`, `RULE_GROUP_ID`, `RATE_RULE_ID` | AWS-style ARNs | Sample WAF identifiers |
| `ACTIONS`, `URIS`, `COUNTRIES`, etc. | Various | Randomized field pools for payload shape |

To point at another host or stream, edit `ENDPOINT` and optionally `HEADERS` and `LOGS_PER_SECOND`.

## Setup

1. **Python:** 3.x (no type hints requiring 3.10+ in this script).
2. **Optional virtualenv:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Dependencies:** `requests` is required but not listed in [`requirements.txt`](requirements.txt):
   ```bash
   pip install requests
   ```

## How to run

1. Install `requests` (see Setup).
2. Optionally edit `ENDPOINT`, `HEADERS`, or `LOGS_PER_SECOND` in [`ingest_logs.py`](ingest_logs.py).
3. From the repo root:
   ```bash
   python ingest_logs.py
   ```
4. The script runs until you stop it with **Ctrl+C**.
5. On success you should see: `Successfully sent 100 WAF match records.` (or your configured batch size) with HTTP 200.

## CLI flags

**None.** This script has no `argparse` interface; it always runs the continuous `send_metrics()` loop.

## Verification

- **Stdout:** `Successfully sent N WAF match records.` when status is 200.
- **Failures:** `Failed! Status: <code>, Body: <text>` or `Network error: ...`.
- Confirm ingestion in your CtrlB staging UI or query layer for the `object_table_bug/v3` stream.

## Related scripts

- [`ingest_logs2.md`](ingest_logs2.md) — flat escape-character test logs to a different CtrlB stream.
- [`ingest_nr_logs.md`](ingest_nr_logs.md) — sends the same WAF payloads (via `generate_waf_match()`) to the New Relic Log API.
