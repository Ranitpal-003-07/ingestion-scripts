from __future__ import annotations

import logging
import os

SERVICES = ("demo-api", "demo-orders", "demo-payments")

# Two instances per service; region split across services for multiseries tests.
SERIES = (
    {"service": "demo-api", "instance": "demo-api-1", "env": "demo", "region": "us-east-1"},
    {"service": "demo-api", "instance": "demo-api-2", "env": "demo", "region": "us-east-1"},
    {"service": "demo-orders", "instance": "demo-orders-1", "env": "demo", "region": "eu-west-1"},
    {"service": "demo-orders", "instance": "demo-orders-2", "env": "demo", "region": "eu-west-1"},
    {"service": "demo-payments", "instance": "demo-payments-1", "env": "demo", "region": "eu-west-1"},
    {"service": "demo-payments", "instance": "demo-payments-2", "env": "demo", "region": "us-east-1"},
)

DEFAULT_EXPORT_INTERVAL_SECONDS = 5
DEFAULT_TICKS_PER_SECOND = 1

MODES = (
    "baseline",
    "spike_cpu",
    "spike_errors",
    "spike_latency",
    "down",
    "recover",
)


def _clean_env(value: str) -> str:
    return value.strip().strip('"').strip("'")


OTLP_ENDPOINT = _clean_env(
    os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "https://staging.ctrlb.dev/engine/api/default")
).rstrip("/")
OTLP_METRICS_ENDPOINT = _clean_env(
    os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    or os.environ.get("OTLP_METRICS_ENDPOINT", "")
)
_LICENSE_KEY_RAW = os.environ.get("NEW_RELIC_LICENSE_KEY", "")
LICENSE_KEY = _clean_env(_LICENSE_KEY_RAW)
OTLP_AUTH_HEADER = _clean_env(os.environ.get("OTLP_AUTH_HEADER", "")) or "api-key"
OTLP_AUTH_TOKEN = _clean_env(os.environ.get("OTLP_AUTH_TOKEN", LICENSE_KEY))
STREAM_HEADER_KEY = _clean_env(os.environ.get("STREAM_HEADER_KEY", "")) or "stream-name"
STREAM_NAME = _clean_env(os.environ.get("STREAM_NAME", ""))
DEPLOYMENT_ENV = _clean_env(os.environ.get("DEPLOYMENT_ENV", "demo")) or "demo"

EXPORT_INTERVAL_SECONDS = DEFAULT_EXPORT_INTERVAL_SECONDS
TICKS_PER_SECOND = DEFAULT_TICKS_PER_SECOND


def is_new_relic_backend() -> bool:
    endpoint = OTLP_METRICS_ENDPOINT or OTLP_ENDPOINT
    return "nr-data.net" in endpoint


def is_ctrlb_backend() -> bool:
    endpoint = (OTLP_METRICS_ENDPOINT or OTLP_ENDPOINT).lower()
    return "ctrlb" in endpoint or bool(STREAM_NAME)


def _parse_otlp_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


def resolve_metrics_endpoint() -> str:
    if OTLP_METRICS_ENDPOINT:
        return OTLP_METRICS_ENDPOINT.rstrip("/")
    return f"{OTLP_ENDPOINT}/v1/metrics"


def build_otlp_headers() -> dict[str, str]:
    headers = _parse_otlp_headers(
        _clean_env(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""))
    )
    explicit_token = bool(_clean_env(os.environ.get("OTLP_AUTH_TOKEN", "")))
    if OTLP_AUTH_TOKEN and OTLP_AUTH_HEADER not in headers:
        if is_new_relic_backend() or explicit_token:
            headers[OTLP_AUTH_HEADER] = OTLP_AUTH_TOKEN
    if STREAM_NAME and STREAM_HEADER_KEY not in headers:
        headers[STREAM_HEADER_KEY] = STREAM_NAME
    return headers


def configure_export_interval(cli_interval: float | None = None) -> float:
    global EXPORT_INTERVAL_SECONDS

    if cli_interval is not None:
        value = float(cli_interval)
        source = "--interval"
    else:
        raw = os.environ.get("METRICS_EXPORT_INTERVAL_SECONDS", str(DEFAULT_EXPORT_INTERVAL_SECONDS))
        source = (
            "METRICS_EXPORT_INTERVAL_SECONDS env"
            if "METRICS_EXPORT_INTERVAL_SECONDS" in os.environ
            else "default"
        )
        value = float(raw)

    if value < 1:
        raise SystemExit(f"Export interval must be >= 1 second, got {value} from {source}")

    EXPORT_INTERVAL_SECONDS = value
    return value


def configure_ticks_per_second(cli_rate: int | None = None) -> int:
    global TICKS_PER_SECOND

    if cli_rate is not None:
        value = int(cli_rate)
        source = "--rate"
    else:
        raw = os.environ.get("METRICS_TICKS_PER_SECOND", str(DEFAULT_TICKS_PER_SECOND))
        source = (
            "METRICS_TICKS_PER_SECOND env"
            if "METRICS_TICKS_PER_SECOND" in os.environ
            else "default"
        )
        value = int(raw)

    if value < 1:
        raise SystemExit(f"Ticks per second must be >= 1, got {value} from {source}")

    TICKS_PER_SECOND = value
    return value


def parse_target(raw: str | None) -> dict[str, str]:
    """Parse --target service=demo-api or instance=demo-api-1."""
    if not raw:
        return {}

    if "=" not in raw:
        raise SystemExit(
            f"Invalid --target {raw!r}; use key=value (service=demo-api or instance=demo-api-1)"
        )

    key, value = raw.split("=", 1)
    key = key.strip()
    value = value.strip()
    if key not in ("service", "instance"):
        raise SystemExit(f"Invalid target key {key!r}; use service or instance")
    if not value:
        raise SystemExit(f"Invalid --target {raw!r}; value cannot be empty")

    return {key: value}


def validate_config() -> None:
    if is_new_relic_backend() and not OTLP_AUTH_TOKEN:
        raise SystemExit("NEW_RELIC_LICENSE_KEY is required for New Relic OTLP export.")
    if is_ctrlb_backend() and not STREAM_NAME:
        raise SystemExit(
            "STREAM_NAME is required for CtrlB (sent as stream-name header; "
            "not part of the /v1/metrics URL path)."
        )
    if OTLP_AUTH_TOKEN and any(ch in OTLP_AUTH_TOKEN for ch in "\r\n\t"):
        raise SystemExit(
            "OTLP auth token contains invalid characters (newline/tab). "
            "Re-export on one line."
        )
    if _LICENSE_KEY_RAW != LICENSE_KEY:
        logging.warning(
            "NEW_RELIC_LICENSE_KEY contained leading/trailing whitespace; stripped."
        )
