from __future__ import annotations

import logging
import os
import uuid


def _clean_env(value: str) -> str:
    """Strip whitespace/newlines often introduced when copying keys from files."""
    return value.strip().strip('"').strip("'")


OTLP_ENDPOINT = _clean_env(
    os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otlp.nr-data.net")
).rstrip("/")
OTLP_TRACES_ENDPOINT = _clean_env(
    os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    or os.environ.get("OTLP_TRACES_ENDPOINT", "")
)
OTLP_METRICS_ENDPOINT = _clean_env(
    os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    or os.environ.get("OTLP_METRICS_ENDPOINT", "")
)
_LICENSE_KEY_RAW = os.environ.get("NEW_RELIC_LICENSE_KEY", "")
LICENSE_KEY = _clean_env(_LICENSE_KEY_RAW)
OTLP_AUTH_HEADER = _clean_env(os.environ.get("OTLP_AUTH_HEADER", "api-key")) or "api-key"
OTLP_AUTH_TOKEN = _clean_env(os.environ.get("OTLP_AUTH_TOKEN", LICENSE_KEY))
# CtrlB uses stream-name header; default key when STREAM_NAME is set.
STREAM_HEADER_KEY = _clean_env(os.environ.get("STREAM_HEADER_KEY", "")) or "stream-name"
STREAM_NAME = _clean_env(os.environ.get("STREAM_NAME", ""))
DEPLOYMENT_ENV = _clean_env(os.environ.get("DEPLOYMENT_ENV", "demo")) or "demo"
SERVICE_INSTANCE_ID = os.environ.get("SERVICE_INSTANCE_ID", str(uuid.uuid4()))


def is_new_relic_backend() -> bool:
    endpoint = OTLP_TRACES_ENDPOINT or OTLP_ENDPOINT
    return "nr-data.net" in endpoint


def is_ctrlb_backend() -> bool:
    endpoint = (OTLP_TRACES_ENDPOINT or OTLP_ENDPOINT).lower()
    return "ctrlb" in endpoint or bool(STREAM_NAME)


# Metrics off by default on CtrlB (traces stream); set OTLP_DISABLE_METRICS=0 to enable.
_raw_disable_metrics = _clean_env(os.environ.get("OTLP_DISABLE_METRICS", ""))
if _raw_disable_metrics:
    OTLP_DISABLE_METRICS = _raw_disable_metrics.lower() in ("1", "true", "yes", "on")
elif _clean_env(os.environ.get("OTEL_METRICS_EXPORTER", "")).lower() == "none":
    OTLP_DISABLE_METRICS = True
elif is_ctrlb_backend():
    OTLP_DISABLE_METRICS = True
else:
    OTLP_DISABLE_METRICS = False

DEFAULT_TRACES_PER_SECOND = 5
MAX_TRACES_PER_SECOND = 100
TRACES_PER_SECOND = DEFAULT_TRACES_PER_SECOND


def configure_traces_per_second(cli_rate: int | None = None) -> int:
    """Resolve rate from --rate, then TRACES_PER_SECOND env, then default."""
    global TRACES_PER_SECOND

    if cli_rate is not None:
        raw = str(cli_rate)
        source = "--rate"
    else:
        raw = os.environ.get("TRACES_PER_SECOND", str(DEFAULT_TRACES_PER_SECOND))
        source = "TRACES_PER_SECOND env" if "TRACES_PER_SECOND" in os.environ else "default"

    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid traces/sec from {source}: {raw!r} (must be an integer)"
        ) from exc

    if value < 1:
        raise SystemExit(f"Traces per second must be >= 1, got {value} from {source}")

    if value > MAX_TRACES_PER_SECOND:
        logging.warning(
            "%s=%s is very high; capping at %s traces/sec. "
            "Unset TRACES_PER_SECOND or use: python ingest_traces.py --rate 5",
            source,
            value,
            MAX_TRACES_PER_SECOND,
        )
        value = MAX_TRACES_PER_SECOND

    TRACES_PER_SECOND = value
    return value

SERVICES = (
    "demo-api-gateway",
    "demo-orders-service",
    "demo-inventory-service",
    "demo-payment-service",
    "demo-notification-worker",
    "demo-auth-service",
)

def _parse_otlp_headers(raw: str) -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS: key=value,key2=value2."""
    headers: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


def resolve_traces_endpoint() -> str:
    """Full OTLP traces URL.

    Prefer OTEL_EXPORTER_OTLP_TRACES_ENDPOINT. Otherwise {base}/v1/traces.
    CtrlB/OpenObserve routes the stream via the stream-name header (not
    the /{stream}/_otel/... path used for logs).
    """
    if OTLP_TRACES_ENDPOINT:
        return OTLP_TRACES_ENDPOINT.rstrip("/")
    return f"{OTLP_ENDPOINT}/v1/traces"


def resolve_metrics_endpoint() -> str:
    if OTLP_METRICS_ENDPOINT:
        return OTLP_METRICS_ENDPOINT.rstrip("/")
    return f"{OTLP_ENDPOINT}/v1/metrics"


def build_otlp_headers() -> dict[str, str]:
    """Build OTLP HTTP headers (CtrlB: stream-name only; no auth required)."""
    headers = _parse_otlp_headers(
        _clean_env(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""))
    )
    # CtrlB needs no auth. Only inject api-key for New Relic, or when
    # OTLP_AUTH_TOKEN is set explicitly (not via NEW_RELIC_LICENSE_KEY fallback).
    explicit_token = bool(_clean_env(os.environ.get("OTLP_AUTH_TOKEN", "")))
    if OTLP_AUTH_TOKEN and OTLP_AUTH_HEADER not in headers:
        if is_new_relic_backend() or explicit_token:
            headers[OTLP_AUTH_HEADER] = OTLP_AUTH_TOKEN
    if STREAM_NAME and STREAM_HEADER_KEY not in headers:
        headers[STREAM_HEADER_KEY] = STREAM_NAME
    return headers


def validate_config() -> None:
    if is_new_relic_backend() and not OTLP_AUTH_TOKEN:
        raise SystemExit(
            "NEW_RELIC_LICENSE_KEY is required for New Relic OTLP export."
        )
    if is_ctrlb_backend() and not STREAM_NAME:
        raise SystemExit(
            "STREAM_NAME is required for CtrlB (sent as stream-name header; "
            "not part of the /v1/traces URL path)."
        )
    if _LICENSE_KEY_RAW != LICENSE_KEY:
        logging.warning(
            "NEW_RELIC_LICENSE_KEY contained leading/trailing whitespace; stripped."
        )
    if OTLP_AUTH_TOKEN and any(ch in OTLP_AUTH_TOKEN for ch in "\r\n\t"):
        raise SystemExit(
            "OTLP auth token contains invalid characters (newline/tab). "
            "Re-export on one line."
        )
