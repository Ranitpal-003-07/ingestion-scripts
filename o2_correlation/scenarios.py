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


WORKLOADS: tuple[Workload, ...] = (
    Workload(
        workload_id="k8s-checkout",
        kind=IdentityKind.K8S,
        service="checkout",
        env="prod",
        cluster="prod-us-east",
        namespace="payments",
        prefer_errors=True,
    ),
    Workload(
        workload_id="k8s-cart",
        kind=IdentityKind.K8S,
        service="cart",
        env="prod",
        cluster="prod-us-east",
        namespace="payments",
    ),
    Workload(
        workload_id="aws-checkout",
        kind=IdentityKind.AWS,
        service="checkout",
        env="prod",
        account="111122223333",
        region="us-east-1",
    ),
)


def _micros_now() -> int:
    return int(time.time() * 1_000_000)


def build_log_record(workload: Workload) -> dict[str, Any]:
    """Logs use app / namespace / cluster (K8s) or app / account / region (AWS)."""
    is_error = workload.prefer_errors and random.random() < 0.35
    record: dict[str, Any] = {
        "app": workload.service,
        "env": workload.env,
        "level": "error" if is_error else "info",
        "message": (
            "payment gateway timeout"
            if is_error and workload.service == "checkout"
            else f"{workload.service} request handled"
        ),
        "http_method": random.choice(["GET", "POST"]),
        "uri": random.choice(["/api/v1/checkout", "/api/v1/cart", "/api/v1/health"]),
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
    if workload.service == "checkout":
        return "POST /pay"
    return "GET /cart"


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
    return [build_log_record(w) for w in WORKLOADS]
