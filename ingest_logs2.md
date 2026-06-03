# ingest_logs2.py

## Overview

Continuously generates flat JSON log records that exercise **real tab (`\t`) and newline (`\n`) characters** in string fields (not escaped `\\t` / `\\n` literals). Records cycle through predefined variants to test how the ingest pipeline renders escape characters. Batches are POSTed to a CtrlB staging endpoint.

## Endpoint

| Property | Value |
|----------|-------|
| **URL** | `http://staging.ctrlb.dev:8080/api/default/escape_table_bug/_json_evolving` |
| **Method** | `POST` |
| **Payload** | JSON array of flat log objects (batch size = `LOGS_PER_SECOND` per second) |
| **Timeout** | 10 seconds per request |

Change the URL by editing the `ENDPOINT` constant at the top of [`ingest_logs2.py`](ingest_logs2.py).

## Authentication / headers

No API key. The script sends Postman-style headers:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `Accept` | `*/*` |
| `Accept-Encoding` | `gzip, deflate, br` |
| `Connection` | `keep-alive` |
| `User-Agent` | `PostmanRuntime/7.51.0` |

Configure via the `HEADERS` dict in [`ingest_logs2.py`](ingest_logs2.py).

## Configuration

All settings are **constants in the script** (no environment variables or CLI).

| Constant | Default | Purpose |
|----------|---------|---------|
| `ENDPOINT` | CtrlB staging URL above | Ingest URL |
| `HEADERS` | Postman-style set | HTTP headers |
| `LOGS_PER_SECOND` | `30` | Logs per batch; one batch per second |
| `ESCAPE_TEST_VARIANTS` | 5 variants | Rotating `variant`, `message`, `escape_test_field` content |

Each generated log includes:

- `_timestamp` / `timestamp` — microseconds since epoch
- `body` — variant message (tabs/newlines as configured)
- `escape_test_variant` — variant name (e.g. `tab_only`, `newline_only`)
- `escape_test_field` — second field with tab/newline patterns

## Setup

1. **Python:** 3.x.
2. **Optional virtualenv:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Dependencies:**
   ```bash
   pip install requests
   ```

## How to run

1. Install `requests` (see Setup).
2. Optionally edit `ENDPOINT`, `HEADERS`, `LOGS_PER_SECOND`, or `ESCAPE_TEST_VARIANTS` in [`ingest_logs2.py`](ingest_logs2.py).
3. From the repo root:
   ```bash
   python ingest_logs2.py
   ```
4. Stop with **Ctrl+C**.
5. Every batch prints `Status: <code>`; non-200 responses also print the response body.

## CLI flags

**None.** This script has no `argparse` interface; it always runs the continuous `send_logs()` loop.

## Verification

- **Stdout:** `Status: 200` on success; otherwise `Response: ...` with the error body.
- Confirm ingestion in CtrlB staging for the `escape_table_bug` stream and inspect how tabs/newlines appear in stored fields.

## Related scripts

- [`ingest_logs.md`](ingest_logs.md) — nested WAF payloads to `object_table_bug/v3`.
- [`ingest_nr_logs.md`](ingest_nr_logs.md) — New Relic Log API ingestion (different destination).
