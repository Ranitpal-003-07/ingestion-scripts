"""OpenObserve Cloud ingest configuration."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)


def _clean_env(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _parse_stream_list(
    list_key: str,
    single_key: str,
    default: str = "default",
) -> list[str]:
    """Comma-separated stream names; falls back to single-key env then default."""
    raw = _clean_env(os.environ.get(list_key, ""))
    if not raw:
        raw = _clean_env(os.environ.get(single_key, default))
    streams = [part.strip() for part in raw.split(",") if part.strip()]
    return streams or [default]


O2_BASE_URL = _clean_env(os.environ.get("O2_BASE_URL", "https://api.openobserve.ai")).rstrip(
    "/"
)
O2_ORG = _clean_env(os.environ.get("O2_ORG", ""))
O2_USER = _clean_env(os.environ.get("O2_USER", ""))
O2_PASSWORD = _clean_env(os.environ.get("O2_PASSWORD", ""))
O2_DEPLOYMENT_ENV = _clean_env(os.environ.get("O2_DEPLOYMENT_ENV", "prod")) or "prod"
O2_STREAM_HEADER_KEY = _clean_env(os.environ.get("O2_STREAM_HEADER_KEY", "stream-name")) or (
    "stream-name"
)

O2_LOG_STREAMS = _parse_stream_list("O2_LOG_STREAMS", "O2_LOG_STREAM")
O2_TRACE_STREAMS = _parse_stream_list("O2_TRACE_STREAMS", "O2_TRACE_STREAM")
O2_METRICS_STREAMS = _parse_stream_list("O2_METRICS_STREAMS", "O2_METRICS_STREAM")

DEFAULT_TICKS_PER_SECOND = 1
TICKS_PER_SECOND = DEFAULT_TICKS_PER_SECOND


def logs_json_url(stream_name: str) -> str:
    return f"{O2_BASE_URL}/api/{O2_ORG}/{stream_name}/_json"


def traces_otlp_url() -> str:
    return f"{O2_BASE_URL}/api/{O2_ORG}/v1/traces"


def metrics_otlp_url() -> str:
    return f"{O2_BASE_URL}/api/{O2_ORG}/v1/metrics"


def requests_auth() -> tuple[str, str]:
    return (O2_USER, O2_PASSWORD)


def basic_authorization_header() -> str:
    token = base64.b64encode(f"{O2_USER}:{O2_PASSWORD}".encode()).decode("ascii")
    return f"Basic {token}"


def build_otlp_headers(stream_name: str | None = None) -> dict[str, str]:
    headers = {"Authorization": basic_authorization_header()}
    if stream_name:
        headers[O2_STREAM_HEADER_KEY] = stream_name
    return headers


def configure_ticks_per_second(cli_value: int | None = None) -> int:
    global TICKS_PER_SECOND
    if cli_value is not None:
        TICKS_PER_SECOND = max(1, int(cli_value))
        return TICKS_PER_SECOND
    raw = os.environ.get("TICKS_PER_SECOND", str(DEFAULT_TICKS_PER_SECOND))
    try:
        TICKS_PER_SECOND = max(1, int(raw))
    except ValueError as exc:
        raise SystemExit(f"Invalid TICKS_PER_SECOND: {raw!r}") from exc
    return TICKS_PER_SECOND


def validate_config() -> None:
    missing = []
    if not O2_ORG:
        missing.append("O2_ORG")
    if not O2_USER:
        missing.append("O2_USER")
    if not O2_PASSWORD:
        missing.append("O2_PASSWORD")
    if missing:
        raise SystemExit(
            f"Missing required env vars: {', '.join(missing)}. "
            f"Copy .env.example to .env and set Cloud credentials."
        )
    if any(ch in O2_PASSWORD for ch in "\r\n\t"):
        raise SystemExit("O2_PASSWORD contains invalid whitespace; use a single-line value.")
    if _ENV_PATH.exists():
        logging.debug("Loaded env from %s", _ENV_PATH)
    logging.info(
        "OpenObserve target org=%s base=%s log_streams=%s trace_streams=%s metric_streams=%s",
        O2_ORG,
        O2_BASE_URL,
        O2_LOG_STREAMS,
        O2_TRACE_STREAMS,
        O2_METRICS_STREAMS,
    )
