# django_instrumentation_test1

Second minimal Django app for step-by-step OpenTelemetry testing. **No OTEL packages or config** — add instrumentation manually.

Identical to `django_instrumentation_test` but runs on **port 8081** by default so both can run side by side.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
./run.sh
```

Plain Django dev server only (`--noreload`). No `opentelemetry-instrument` in `run.sh`.

## Endpoints

```bash
curl http://localhost:8081/health
curl http://localhost:8081/roll
curl http://localhost:8081/work
```

| Route | Response |
|-------|----------|
| `GET /health` | `ok` |
| `GET /roll` | Random integer 1–6 |
| `GET /work` | `{"status": "done"}` after simulated latency |

## Project layout note

Settings module: **`config.settings`** (use `config`, not `myproject`, when following docs).

If using `opentelemetry-instrument`, set this **before** starting:

```bash
export DJANGO_SETTINGS_MODULE=config.settings
```

Load `.env` **before** exporting `OTEL_*` vars that reference `INGESTION_HOST`, `STREAM_NAME`, or `API_TOKEN`.
