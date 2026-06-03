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
_LICENSE_KEY_RAW = os.environ.get("NEW_RELIC_LICENSE_KEY", "")
LICENSE_KEY = _clean_env(_LICENSE_KEY_RAW)
DEPLOYMENT_ENV = _clean_env(os.environ.get("DEPLOYMENT_ENV", "demo")) or "demo"
SERVICE_INSTANCE_ID = os.environ.get("SERVICE_INSTANCE_ID", str(uuid.uuid4()))

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

def validate_config() -> None:
    if not LICENSE_KEY:
        raise SystemExit(
            "NEW_RELIC_LICENSE_KEY is required. "
            "Export your New Relic ingest license key before running."
        )
    if _LICENSE_KEY_RAW != LICENSE_KEY:
        logging.warning(
            "NEW_RELIC_LICENSE_KEY contained leading/trailing whitespace; stripped."
        )
    if any(ch in LICENSE_KEY for ch in "\r\n\t"):
        raise SystemExit(
            "NEW_RELIC_LICENSE_KEY contains invalid characters (newline/tab). "
            "Re-export on one line: export NEW_RELIC_LICENSE_KEY='NRAK-...'"
        )
