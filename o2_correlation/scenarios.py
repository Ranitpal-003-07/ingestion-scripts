"""Correlation demo workloads with different field spellings per signal."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class IdentityKind(str, Enum):
    K8S = "k8s"
    AWS = "aws"


@dataclass(frozen=True)
class Workload:
    workload_id: str
    kind: IdentityKind
    service: str
    env: str
    cluster: str | None = None
    namespace: str | None = None
    account: str | None = None
    region: str | None = None
    prefer_errors: bool = False
    # Log volume per tick — GROUP BY service shows relative heights.
    logs_per_tick: int = 1
    # If set, stop emitting this workload after N seconds from process start
    # (shipping drops out of GROUP BY once the query window no longer covers it).
    active_for_seconds: float | None = None


# Process start — used for shipping's short-lived window.
_INGEST_STARTED_AT = time.time()

# Shipping stops after this many seconds so its GROUP BY bucket disappears
# from recent-time queries while checkout/payments/auth keep flowing.
SHIPPING_ACTIVE_SECONDS = 180.0

WORKLOADS: tuple[Workload, ...] = (
    Workload(
        workload_id="k8s-checkout",
        kind=IdentityKind.K8S,
        service="checkout",
        env="prod",
        cluster="prod-us-east",
        namespace="payments",
        prefer_errors=True,
        logs_per_tick=12,
    ),
    Workload(
        workload_id="k8s-payments",
        kind=IdentityKind.K8S,
        service="payments",
        env="prod",
        cluster="prod-us-east",
        namespace="payments",
        logs_per_tick=10,
    ),
    Workload(
        workload_id="k8s-auth",
        kind=IdentityKind.K8S,
        service="auth",
        env="prod",
        cluster="prod-us-east",
        namespace="identity",
        logs_per_tick=1,
    ),
    Workload(
        workload_id="k8s-shipping",
        kind=IdentityKind.K8S,
        service="shipping",
        env="prod",
        cluster="prod-us-east",
        namespace="fulfillment",
        logs_per_tick=6,
        active_for_seconds=SHIPPING_ACTIVE_SECONDS,
    ),
)


def _micros_now() -> int:
    return int(time.time() * 1_000_000)


def ingest_elapsed_seconds() -> float:
    return time.time() - _INGEST_STARTED_AT


def workload_is_active(workload: Workload) -> bool:
    if workload.active_for_seconds is None:
        return True
    return ingest_elapsed_seconds() < workload.active_for_seconds


def active_workloads() -> list[Workload]:
    return [w for w in WORKLOADS if workload_is_active(w)]


def build_log_record(workload: Workload) -> dict[str, Any]:
    """Logs include bare `service` for GROUP BY, plus `app` for field-alias demos."""
    is_error = workload.prefer_errors and random.random() < 0.35
    paths = {
        "checkout": ["/api/v1/checkout", "/api/v1/checkout/confirm"],
        "payments": ["/api/v1/payments", "/api/v1/payments/capture"],
        "auth": ["/api/v1/auth/login", "/api/v1/auth/token"],
        "shipping": ["/api/v1/shipping", "/api/v1/shipping/track"],
    }
    record: dict[str, Any] = {
        "service": workload.service,
        "app": workload.service,
        "env": workload.env,
        "level": "error" if is_error else "info",
        "message": (
            "payment gateway timeout"
            if is_error and workload.service == "checkout"
            else f"{workload.service} request handled"
        ),
        "http_method": random.choice(["GET", "POST"]),
        "uri": random.choice(paths.get(workload.service, ["/api/v1/health"])),
        "_timestamp": _micros_now(),
        "workload_id": workload.workload_id,
    }
    if workload.kind == IdentityKind.K8S:
        record["namespace"] = workload.namespace
        record["cluster"] = workload.cluster
    else:
        record["account"] = workload.account
        record["region"] = workload.region
    return record


def build_trace_resource_attributes(workload: Workload) -> dict[str, str]:
    """OTel resource attrs. OpenObserve stores service.name as service_name;
    other resource keys become service_<key> with dots → underscores
    (e.g. k8s.namespace.name → service_k8s_namespace_name). Prefer span attrs
    for correlation dims so they match log/metric field names."""
    return {
        "service.name": workload.service,
        "deployment.environment": workload.env,
    }


def build_trace_span_attributes(workload: Workload) -> dict[str, str]:
    """Span attrs use the same bare keys as logs/metrics (app, namespace, …).
    OpenObserve flattens them to attributes_<key> on the stored span; the UI
    peels that prefix (and field-aliases.correlation.json lists both spellings).
    """
    attrs = {
        "service": workload.service,
        "app": workload.service,
        "env": workload.env,
        "workload_id": workload.workload_id,
    }
    if workload.kind == IdentityKind.K8S:
        attrs["namespace"] = workload.namespace or ""
        attrs["cluster"] = workload.cluster or ""
    else:
        attrs["account"] = workload.account or ""
        attrs["region"] = workload.region or ""
    return attrs


def build_trace_span_name(workload: Workload) -> str:
    names = {
        "checkout": "POST /checkout",
        "payments": "POST /payments",
        "auth": "POST /auth/login",
        "shipping": "GET /shipping",
    }
    return names.get(workload.service, f"GET /{workload.service}")


def trace_should_fail(workload: Workload) -> bool:
    return workload.prefer_errors and random.random() < 0.25


def build_metric_attributes(workload: Workload) -> dict[str, str]:
    """Metrics use service / namespace / cluster or service / account / region."""
    attrs = {"service": workload.service, "env": workload.env}
    if workload.kind == IdentityKind.K8S:
        attrs["namespace"] = workload.namespace or ""
        attrs["cluster"] = workload.cluster or ""
    else:
        attrs["account"] = workload.account or ""
        attrs["region"] = workload.region or ""
    return attrs


def metric_cpu_ratio(workload: Workload) -> float:
    if workload.prefer_errors:
        return round(random.uniform(0.65, 0.92), 3)
    return round(random.uniform(0.15, 0.45), 3)


def metric_request_count(workload: Workload) -> int:
    return random.randint(5, 25)


def all_log_batch() -> list[dict[str, Any]]:
    """Weighted log batch: checkout/payments high, auth low; shipping timed out."""
    records: list[dict[str, Any]] = []
    for workload in WORKLOADS:
        if not workload_is_active(workload):
            continue
        for _ in range(max(1, workload.logs_per_tick)):
            records.append(build_log_record(workload))
    return records
