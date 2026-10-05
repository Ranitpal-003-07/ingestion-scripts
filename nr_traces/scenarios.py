"""Synthetic APM scenarios for Transactions / Database / External tabs.

Designed for CtrlB staging coverage:
  - >500 peers / txns / DB ops / instance IDs (see catalog.py)
  - Dual-type peers (payments/inventory HTTP+gRPC)
  - DB vs External split (db_system set vs empty)
  - Peer naming edges (peer_service only, net_peer_name only, conflict, nameless)
  - HTTP 4xx/5xx without OTel ERROR + OTel ERROR peers + healthy 200s
  - Slow/fast peers for P99 ranks
  - Time-spread via backdated start/end timestamps
  - Empty-external service (SERVER only)
"""

from __future__ import annotations

import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from nr_traces import attrs, catalog, config, ids
from nr_traces.catalog import (
    EMPTY_EXTERNAL_SERVICE,
    ENTITY_TYPE_PERCENT,
    ENTITY_TYPE_RECIPES,
    NO_DB_SCHEMA_SERVICE,
    PRIMARY_SERVICE,
    DbOp,
    PeerSpec,
    TxnSpec,
    pick_db_op,
    pick_entity_type_peer,
    pick_instance_id,
    pick_peer,
    pick_transaction,
)
from nr_traces.ids import (
    format_trace_id,
    random_amount_cents,
    random_customer_id,
    random_order_id,
    random_sku,
)
from nr_traces.otlp import OtlpSession

ScenarioFn = Callable[[OtlpSession], str]


@dataclass
class Biz:
    customer_id: str = field(default_factory=random_customer_id)
    order_id: str = field(default_factory=random_order_id)
    sku: str = field(default_factory=random_sku)
    session_id: str = field(default_factory=ids.random_session_id)
    tenant_id: str = field(default_factory=ids.random_tenant)
    region: str = field(default_factory=ids.random_region)
    feature_flag: str = field(
        default_factory=lambda: random.choice(ids.FEATURE_FLAGS)
    )
    experiment_id: str = field(
        default_factory=lambda: random.choice(ids.EXPERIMENTS)
    )
    request_id: str = field(default_factory=ids.random_request_id)
    user_agent: str = field(default_factory=ids.random_user_agent)
    client_ip: str = field(default_factory=lambda: ids.random_ip(private=False))
    currency: str = field(default_factory=ids.random_currency)
    payment_method: str = field(default_factory=ids.random_payment_method)
    amount_cents: int = field(default_factory=random_amount_cents)
    user_email: str = field(default="")
    key: str = field(default_factory=ids.random_span_key)

    def __post_init__(self) -> None:
        if not self.user_email:
            self.user_email = ids.random_email(self.customer_id)

    def span_attrs(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return attrs.business(
            customer_id=self.customer_id,
            order_id=self.order_id,
            sku=self.sku,
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            region=self.region,
            feature_flag=self.feature_flag,
            experiment_id=self.experiment_id,
            request_id=self.request_id,
            user_email=self.user_email,
            extra={
                "cart.currency": self.currency,
                "payment.method": self.payment_method,
                "order.amount_cents": self.amount_cents,
                # CtrlB custom columns (also queryable as key / timestamp)
                "key": self.key,
                "timestamp": ids.now_timestamp_us(),
                **(extra or {}),
            },
        )


def _merge(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in parts:
        out.update(part)
    return out


def _mark_error(span, message: str, exc: BaseException | None = None) -> None:
    span.set_status(Status(StatusCode.ERROR, message))
    if exc is not None:
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        span.set_attribute("error.message", str(exc))
    else:
        span.set_attribute("error.type", "Error")
        span.set_attribute("error.message", message)


def _age_ns() -> int:
    """Random age within TIME_SPREAD_MINUTES for chart bucket coverage."""
    minutes = max(0, config.TIME_SPREAD_MINUTES)
    if minutes <= 0:
        return 0
    # Bias toward recent (last 15m) but still fill older buckets.
    if random.random() < 0.55:
        span_min = random.uniform(0, min(15, minutes))
    else:
        span_min = random.uniform(0, minutes)
    return int(span_min * 60 * 1_000_000_000)


def _duration_ns(lo_ms: float, hi_ms: float) -> int:
    return int(random.uniform(lo_ms, hi_ms) * 1_000_000)


@contextmanager
def _timed_span(
    tracer,
    name: str,
    *,
    kind: SpanKind,
    attributes: dict[str, Any],
    start_ns: int,
    duration_ns: int,
    parent_ctx=None,
) -> Iterator[Any]:
    """Start/end with explicit timestamps (no wall-clock sleep)."""
    span = tracer.start_span(
        name,
        kind=kind,
        attributes=attributes,
        context=parent_ctx,
        start_time=start_ns,
    )
    token = otel_context.attach(trace.set_span_in_context(span))
    try:
        yield span
    finally:
        span.end(end_time=start_ns + duration_ns)
        otel_context.detach(token)


def _http_status_for_peer(peer: PeerSpec) -> tuple[int, bool]:
    """Return (http_status, otel_error).

    Distinguishes:
      - HTTP-aware errors (4xx/5xx, no OTel ERROR)
      - OTel ERROR (status ERROR)
      - Healthy 200
    """
    if random.random() < peer.error_rate:
        return random.choice((500, 502, 503)), True
    if random.random() < peer.http_error_rate:
        return random.choice((400, 404, 422, 500, 502)), False
    return 200, False


def _strip_db(attrs_map: dict[str, Any]) -> dict[str, Any]:
    attrs_map.pop("db.system", None)
    attrs_map.pop("db.system.name", None)
    return attrs_map


def _root_txn_attrs(txn: TxnSpec, biz: Biz, status_code: int = 200) -> tuple[SpanKind, dict[str, Any]]:
    """Build SERVER/CONSUMER attributes for a multi-protocol transaction."""
    kind = txn.kind

    if kind == "http":
        method = txn.http_method or "GET"
        route = txn.http_route or "/"
        return SpanKind.SERVER, _merge(
            attrs.http_server(
                method=method,
                route=route,
                status_code=status_code,
                scheme=txn.http_scheme or "https",
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
            ),
            biz.span_attrs({"txn.protocol": "http"}),
        )

    if kind in ("grpc", "connect_rpc", "dubbo"):
        rpc_attrs = attrs.rpc_client(
            system=txn.rpc_system or kind,
            service=txn.rpc_service or "Service",
            method=txn.rpc_method or "Call",
            peer="0.0.0.0",
            port=50051 if kind == "grpc" else 8080,
            grpc_status=0 if kind == "grpc" else None,
            peer_service=None,
        )
        rpc_attrs.pop("peer.service", None)
        for key in list(rpc_attrs):
            if key.startswith("http.") or key.startswith("url.") or key.startswith("messaging."):
                rpc_attrs.pop(key, None)
        return SpanKind.SERVER, _merge(rpc_attrs, biz.span_attrs({"txn.protocol": kind}))

    if kind == "graphql":
        route = txn.http_route or "/graphql"
        g = attrs.http_server(
            method=txn.http_method or "POST",
            route=route,
            status_code=status_code,
            scheme=txn.http_scheme or "https",
            user_agent=biz.user_agent,
            client_ip=biz.client_ip,
        )
        g.update(
            {
                "graphql.operation.name": txn.graphql_operation or "Anonymous",
                "graphql.operation.type": txn.graphql_type or "query",
                "graphql.document": (
                    f"{txn.graphql_type or 'query'} {txn.graphql_operation or 'Anonymous'} {{ ... }}"
                ),
            }
        )
        return SpanKind.SERVER, _merge(g, biz.span_attrs({"txn.protocol": "graphql"}))

    if kind in ("kafka", "rabbitmq", "sqs") or txn.messaging_system:
        system = txn.messaging_system or kind
        dest = txn.messaging_destination or txn.name
        op = txn.messaging_operation or "process"
        msg = attrs.messaging(
            system=system,
            destination=dest,
            operation=op,
            destination_kind="queue" if system in ("sqs", "rabbitmq") else "topic",
            peer_service=None,
        )
        msg.pop("peer.service", None)
        for key in list(msg):
            if key.startswith("http.") or key.startswith("url.") or key.startswith("graphql."):
                msg.pop(key, None)
        return SpanKind.CONSUMER, _merge(msg, biz.span_attrs({"txn.protocol": system}))

    if kind == "websocket":
        route = txn.http_route or "/ws"
        ws = attrs.http_server(
            method="GET",
            route=route,
            status_code=101,
            scheme="https",
            user_agent=biz.user_agent,
            client_ip=biz.client_ip,
        )
        ws.update(
            {
                "messaging.system": "websocket",
                "messaging.operation": "receive",
                "messaging.destination": route,
                "messaging.destination.name": route,
            }
        )
        return SpanKind.SERVER, _merge(ws, biz.span_attrs({"txn.protocol": "websocket"}))

    return SpanKind.SERVER, biz.span_attrs({"txn.protocol": "other"})


def _emit_external_client(
    session: OtlpSession,
    *,
    tracer,
    parent_ctx,
    peer: PeerSpec,
    biz: Biz,
    start_ns: int,
) -> float:
    """Emit one CLIENT/PRODUCER span for External tab. Returns duration seconds."""
    duration_ns = _duration_ns(*peer.latency_ms)
    duration_s = duration_ns / 1e9
    kind = peer.kind

    if kind == "nameless":
        with _timed_span(
            tracer,
            "CLIENT anonymous",
            kind=SpanKind.CLIENT,
            attributes=_merge(
                {
                    "http.request.method": "GET",
                    "http.method": "GET",
                    "http.response.status_code": 200,
                    "http.status_code": 200,
                },
                biz.span_attrs(),
            ),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ):
            pass
        return duration_s

    # --- HTTP family (http / https / peer naming edges) ---
    if kind in ("http", "https", "peer_only", "net_only", "conflict"):
        status, otel_err = _http_status_for_peer(peer)
        # Recipe: payments HTTP → GET /charge for entity_type=http discovery
        if peer.peer_service == "payments" and peer.route == "/charge":
            method = "GET"
            route = "/charge"
        else:
            method = random.choice(("GET", "POST", "PUT", "PATCH"))
            route = peer.route or f"/v1/{peer.name or 'call'}"
        host = peer.host or "unknown.demo.internal"
        scheme = peer.scheme or ("https" if kind == "https" or peer.port == 443 else "http")
        flavor = peer.flavor or ("2.0" if scheme == "https" else "1.1")
        url = f"{scheme}://{host}{route}"

        client_attrs = attrs.http_client(
            method=method,
            url=url,
            status_code=status,
            peer=peer.net_peer_name or host or None,
            port=peer.port or None,
            peer_service=peer.peer_service,
            flavor=flavor,
        )
        # Ensure classic HTTP discovery columns are present
        client_attrs["http.method"] = method
        client_attrs["http.request.method"] = method
        client_attrs["http.route"] = route
        client_attrs["http.target"] = route
        if kind == "peer_only":
            client_attrs.pop("net.peer.name", None)
            client_attrs.pop("server.address", None)
            if peer.peer_service:
                client_attrs["peer.service"] = peer.peer_service
        elif kind == "net_only":
            client_attrs.pop("peer.service", None)
            if peer.net_peer_name:
                client_attrs["net.peer.name"] = peer.net_peer_name
                client_attrs["server.address"] = peer.net_peer_name
        elif kind == "conflict":
            if peer.peer_service:
                client_attrs["peer.service"] = peer.peer_service
            if peer.net_peer_name:
                client_attrs["net.peer.name"] = peer.net_peer_name
                client_attrs["server.address"] = peer.net_peer_name

        _strip_db(client_attrs)
        with _timed_span(
            tracer,
            f"{method} {peer.name or host}",
            kind=SpanKind.CLIENT,
            attributes=_merge(client_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ) as span:
            if otel_err:
                _mark_error(
                    span,
                    f"{peer.name or host} failed",
                    RuntimeError(f"upstream returned {status}"),
                )
        session.record_http_client(
            service_name=PRIMARY_SERVICE,
            duration_s=duration_s,
            method=method,
            url=url,
            status_code=status,
        )
        return duration_s

    if kind == "graphql":
        status, otel_err = _http_status_for_peer(peer)
        host = peer.host
        url = f"{peer.scheme or 'https'}://{host}{peer.route or '/graphql'}"
        g_attrs = attrs.graphql_client(
            url=url,
            operation_name=peer.graphql_operation or "Anonymous",
            operation_type=peer.graphql_type or "query",
            status_code=status,
            peer_service=peer.peer_service or peer.name,
        )
        # graphql_http: HTTP fields + GraphQL fields
        g_attrs["http.method"] = "POST"
        g_attrs["http.request.method"] = "POST"
        g_attrs["http.route"] = peer.route or "/graphql"
        _strip_db(g_attrs)
        with _timed_span(
            tracer,
            f"GraphQL {peer.graphql_operation or peer.name}",
            kind=SpanKind.CLIENT,
            attributes=_merge(g_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ) as span:
            if otel_err:
                _mark_error(span, "graphql error", RuntimeError("GraphQL upstream error"))
        return duration_s

    if kind == "soap":
        status, otel_err = _http_status_for_peer(peer)
        host = peer.host
        url = f"{peer.scheme or 'https'}://{host}{peer.route or '/soap'}"
        s_attrs = attrs.soap_client(
            url=url,
            action=peer.soap_action or "Execute",
            status_code=status,
            peer_service=peer.peer_service or peer.name,
        )
        _strip_db(s_attrs)
        with _timed_span(
            tracer,
            f"SOAP {peer.soap_action or peer.name}",
            kind=SpanKind.CLIENT,
            attributes=_merge(s_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ) as span:
            if otel_err:
                _mark_error(span, "soap fault", RuntimeError("SOAP Fault"))
        return duration_s

    if kind == "websocket":
        url = f"{peer.scheme or 'wss'}://{peer.host}{peer.route or '/ws'}"
        ws_attrs = attrs.websocket_client(
            url=url,
            peer_service=peer.peer_service or peer.name,
        )
        _strip_db(ws_attrs)
        with _timed_span(
            tracer,
            f"WS {peer.name}",
            kind=SpanKind.CLIENT,
            attributes=_merge(ws_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ):
            pass
        return duration_s

    # --- RPC family ---
    if kind in ("grpc", "connect_rpc", "dubbo", "jsonrpc", "java_rmi"):
        rpc_system = peer.rpc_system or {
            "grpc": "grpc",
            "connect_rpc": "connect_rpc",
            "dubbo": "apache_dubbo",
            "jsonrpc": "jsonrpc",
            "java_rmi": "java_rmi",
        }[kind]
        otel_err = random.random() < peer.error_rate
        grpc_status = None
        if kind == "grpc":
            grpc_status = random.choice((2, 4, 13, 14)) if otel_err else 0
        rpc_attrs = attrs.rpc_client(
            system=rpc_system,
            service=peer.rpc_service or f"{peer.name}.Service",
            method=peer.rpc_method or "Call",
            peer=peer.host,
            port=peer.port,
            grpc_status=grpc_status,
            peer_service=peer.peer_service or peer.name,
        )
        _strip_db(rpc_attrs)
        # entity_type=grpc: avoid HTTP fields on these spans
        for key in list(rpc_attrs):
            if (
                key.startswith("http.")
                or key.startswith("url.")
                or key.startswith("graphql.")
                or key.startswith("messaging.")
            ):
                rpc_attrs.pop(key, None)
        with _timed_span(
            tracer,
            f"{peer.rpc_service or peer.name}/{peer.rpc_method or 'Call'}",
            kind=SpanKind.CLIENT,
            attributes=_merge(rpc_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ) as span:
            if otel_err:
                _mark_error(
                    span,
                    f"{rpc_system} call failed",
                    RuntimeError(f"{rpc_system} error"),
                )
        return duration_s

    # --- Messaging family ---
    if kind in ("kafka", "rabbitmq", "sqs", "sns", "nats", "mqtt", "pulsar"):
        system = peer.messaging_system or kind
        dest = peer.messaging_destination or peer.name
        op = peer.messaging_operation or "publish"
        msg_attrs = attrs.messaging(
            system=system,
            destination=dest,
            operation=op,
            destination_kind=peer.messaging_kind or "topic",
            region=peer.aws_region,
            peer_service=peer.peer_service or system,
            peer_host=peer.host,
            peer_port=peer.port,
        )
        _strip_db(msg_attrs)
        # entity_type=kafka: no HTTP / GraphQL noise
        for key in list(msg_attrs):
            if key.startswith("http.") or key.startswith("url.") or key.startswith("graphql."):
                msg_attrs.pop(key, None)
        # Hard rule: External spans use span_kind=CLIENT (3)
        with _timed_span(
            tracer,
            f"{op} {dest}",
            kind=SpanKind.CLIENT,
            attributes=_merge(msg_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ):
            pass
        return duration_s

    # --- AWS ---
    if kind == "aws_s3":
        region = peer.aws_region or biz.region
        bucket = peer.s3_bucket or "demo-order-receipts"
        key = (peer.s3_key or "receipts/{order_id}.pdf").replace("{order_id}", biz.order_id)
        status, otel_err = _http_status_for_peer(peer)
        s3_attrs = attrs.s3_client(
            operation=peer.aws_operation or "PutObject",
            bucket=bucket,
            key=key,
            region=region,
            status_code=status,
        )
        if peer.peer_service:
            s3_attrs["peer.service"] = peer.peer_service
        _strip_db(s3_attrs)
        with _timed_span(
            tracer,
            f"S3 {peer.aws_operation or 'PutObject'}",
            kind=SpanKind.CLIENT,
            attributes=_merge(s3_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ) as span:
            if otel_err:
                _mark_error(span, "s3 error", RuntimeError("S3 request failed"))
        return duration_s

    if kind == "aws_api":
        status, otel_err = _http_status_for_peer(peer)
        aws_attrs = attrs.aws_api_client(
            service=peer.aws_service or "dynamodb",
            operation=peer.aws_operation or "GetItem",
            region=peer.aws_region or biz.region,
            peer_service=peer.peer_service or f"aws.{peer.aws_service or 'dynamodb'}",
            status_code=status,
        )
        _strip_db(aws_attrs)
        with _timed_span(
            tracer,
            f"AWS {peer.aws_service}/{peer.aws_operation}",
            kind=SpanKind.CLIENT,
            attributes=_merge(aws_attrs, biz.span_attrs()),
            start_ns=start_ns,
            duration_ns=duration_ns,
            parent_ctx=parent_ctx,
        ) as span:
            if otel_err:
                _mark_error(span, "aws api error", RuntimeError("AWS API error"))
        return duration_s

    # other — peer_service only; no http / grpc / kafka / graphql fields
    other_attrs: dict[str, Any] = {
        "peer.service": peer.peer_service or peer.name or "mystery-peer",
    }
    if peer.net_peer_name or peer.host:
        other_attrs["net.peer.name"] = peer.net_peer_name or peer.host
        other_attrs["server.address"] = peer.net_peer_name or peer.host
        if peer.port:
            other_attrs["server.port"] = peer.port
    with _timed_span(
        tracer,
        f"call {peer.name or 'mystery-peer'}",
        kind=SpanKind.CLIENT,
        attributes=_merge(other_attrs, biz.span_attrs()),
        start_ns=start_ns,
        duration_ns=duration_ns,
        parent_ctx=parent_ctx,
    ):
        pass
    return duration_s


def _emit_db_client(
    session: OtlpSession,
    *,
    tracer,
    parent_ctx,
    op: DbOp,
    biz: Biz,
    start_ns: int,
    omit_db_system: bool = False,
) -> float:
    """Emit a CLIENT span with DB attributes.

    When omit_db_system=True (demo-edge-bff), keep db.operation / db.statement /
    peer naming but strip db.system so Database tab soft-fails / External overlap.
    """
    duration_ns = _duration_ns(*op.latency_ms)
    duration_s = duration_ns / 1e9
    db_attrs: dict[str, Any]
    if op.system == "redis":
        db_attrs = attrs.redis_client(
            operation=op.operation,
            statement=op.statement,
            namespace=op.table,
            peer=op.peer,
        )
    elif op.system == "elasticsearch":
        db_attrs = attrs.elasticsearch_client(
            operation=op.operation,
            statement=op.statement,
            index=op.table,
            peer=op.peer,
        )
    elif op.system == "mongodb":
        db_attrs = attrs.db_client(
            system="mongodb",
            operation=op.operation,
            statement=op.statement,
            db_name=op.db_name,
            mongodb_collection=op.table,
            peer=op.peer,
        )
    else:
        db_attrs = attrs.db_client(
            system=op.system,
            operation=op.operation,
            statement=op.statement,
            db_name=op.db_name,
            sql_table=op.table,
            peer=op.peer,
            rows_affected=random.randint(0, 12),
        )
    # DB clients also set peer.service (tracer-style) — must still land in Database.
    db_attrs["peer.service"] = op.peer.split(".")[0]

    if omit_db_system:
        db_attrs.pop("db.system", None)
        db_attrs.pop("db.system.name", None)

    otel_err = random.random() < op.error_rate
    if otel_err:
        db_attrs["db.response.status_code"] = "500"

    with _timed_span(
        tracer,
        f"{op.operation} {op.table}",
        kind=SpanKind.CLIENT,
        attributes=_merge(db_attrs, biz.span_attrs()),
        start_ns=start_ns,
        duration_ns=duration_ns,
        parent_ctx=parent_ctx,
    ) as span:
        if otel_err:
            _mark_error(
                span,
                "db query failed",
                RuntimeError(f"{op.system} error on {op.table}"),
            )
    return duration_s


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def checkout_external_heavy(session: OtlpSession) -> str:
    """PRIMARY busy service: multi-protocol SERVER/CONSUMER txn + External + DB.

    Transaction mix (fixed): http 35% / grpc 25% / kafka 15% / graphql 10% / …
    External mix (fixed): http 40% / grpc 25% / kafka 15% / graphql_http 10% / other 10%.
    """
    biz = Biz()
    instance = pick_instance_id(PRIMARY_SERVICE)
    tracer = session.tracer(PRIMARY_SERVICE, instance)
    txn = pick_transaction()
    age = _age_ns()
    now = time.time_ns()
    root_start = now - age

    n_ext = random.choices((2, 3, 4, 5), weights=(10, 35, 35, 20), k=1)[0]
    n_db = random.choices((0, 1, 2), weights=(25, 50, 25), k=1)[0]

    child_plan: list[tuple[str, Any]] = []
    for _ in range(n_ext):
        child_plan.append(("ext", pick_entity_type_peer()))
    for _ in range(n_db):
        child_plan.append(("db", pick_db_op()))
    random.shuffle(child_plan)

    total_child_ms = sum(random.uniform(*spec.latency_ms) for _, spec in child_plan)
    root_duration_ns = _duration_ns(total_child_ms + 5, total_child_ms + 40)

    server_status = 200
    if random.random() < 0.04:
        server_status = random.choice((500, 502))
    elif random.random() < 0.06:
        server_status = random.choice((400, 404, 422))

    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=server_status)
    if span_kind != SpanKind.SERVER:
        # CONSUMER txns: keep OK unless we explicitly error
        server_status = 200

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=_merge(
            root_attrs,
            attrs.code_location(namespace="checkout.handlers", function="handle"),
        ),
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id
        if server_status >= 500 and span_kind == SpanKind.SERVER:
            _mark_error(root, "request failed")

        parent = session.parent_context(trace_id, root_span_id)
        cursor = root_start + 1_000_000
        for kind, spec in child_plan:
            if kind == "ext":
                d = _emit_external_client(
                    session,
                    tracer=tracer,
                    parent_ctx=parent,
                    peer=spec,
                    biz=biz,
                    start_ns=cursor,
                )
            else:
                d = _emit_db_client(
                    session,
                    tracer=tracer,
                    parent_ctx=parent,
                    op=spec,
                    biz=biz,
                    start_ns=cursor,
                )
            cursor += int(d * 1e9) + 500_000

    if txn.kind == "http":
        session.record_http_server(
            service_name=PRIMARY_SERVICE,
            duration_s=root_duration_ns / 1e9,
            method=txn.http_method or "GET",
            route=txn.http_route or "/",
            status_code=server_status,
        )
    elif txn.messaging_system:
        session.record_messaging_process(
            service_name=PRIMARY_SERVICE,
            duration_s=root_duration_ns / 1e9,
            system=txn.messaging_system,
            destination=txn.messaging_destination or txn.name,
        )
    return format_trace_id(trace_id)


def entity_type_demo(session: OtlpSession) -> str:
    """Emit all required entity_type recipes under a multi-protocol txn root.

    Always includes: payments/http, payments/grpc, inventory/grpc, orders-bus/kafka,
    catalog-graphql/graphql_http, mystery-peer/other, plus DB negative checks.
    Root txn mix: http 35% / grpc 25% / kafka 15% / graphql 10% / …
    """
    biz = Biz()
    tracer = session.tracer(PRIMARY_SERVICE, pick_instance_id(PRIMARY_SERVICE))
    txn = pick_transaction()
    age = _age_ns()
    root_start = time.time_ns() - age

    recipe_peers = (
        ENTITY_TYPE_RECIPES["http"],           # payments + HTTP → http
        ENTITY_TYPE_RECIPES["grpc_payments"],  # payments + gRPC → dual-type row
        ENTITY_TYPE_RECIPES["grpc"],           # inventory + gRPC → grpc
        ENTITY_TYPE_RECIPES["kafka"],          # orders-bus → kafka
        ENTITY_TYPE_RECIPES["graphql_http"],   # → graphql_http
        ENTITY_TYPE_RECIPES["other"],          # mystery-peer → other
        ENTITY_TYPE_RECIPES["http_slow"],      # slow for ranks
        ENTITY_TYPE_RECIPES["http_fast"],
        ENTITY_TYPE_RECIPES["http_errors"],    # HTTP 4xx/5xx without OTel ERROR
    )
    db_ops = [pick_db_op(), pick_db_op()]  # Database negative check

    total_ms = sum(random.uniform(*p.latency_ms) for p in recipe_peers)
    total_ms += sum(random.uniform(*o.latency_ms) for o in db_ops)
    root_duration_ns = _duration_ns(total_ms + 10, total_ms + 50)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=_merge(
            root_attrs,
            biz.span_attrs(
                {
                    "scenario": "entity_type_demo",
                    "entity_type.mix": str(ENTITY_TYPE_PERCENT),
                }
            ),
        ),
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 1_000_000
        for peer in recipe_peers:
            d = _emit_external_client(
                session, tracer=tracer, parent_ctx=parent, peer=peer, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 300_000
        for op in db_ops:
            d = _emit_db_client(
                session, tracer=tracer, parent_ctx=parent, op=op, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 300_000

    if txn.kind == "http":
        session.record_http_server(
            service_name=PRIMARY_SERVICE,
            duration_s=root_duration_ns / 1e9,
            method=txn.http_method or "POST",
            route=txn.http_route or "/api/v1/checkout",
            status_code=200,
        )
    elif txn.messaging_system:
        session.record_messaging_process(
            service_name=PRIMARY_SERVICE,
            duration_s=root_duration_ns / 1e9,
            system=txn.messaging_system,
            destination=txn.messaging_destination or txn.name,
        )
    return format_trace_id(trace_id)


def dual_type_peer_trace(session: OtlpSession) -> str:
    """payments as HTTP + gRPC in one trace (table: two rows, chart may merge)."""
    biz = Biz()
    tracer = session.tracer(PRIMARY_SERVICE, pick_instance_id(PRIMARY_SERVICE))
    txn = pick_transaction()
    chosen = (
        ENTITY_TYPE_RECIPES["http"],
        ENTITY_TYPE_RECIPES["grpc_payments"],
    )
    age = _age_ns()
    root_start = time.time_ns() - age
    root_duration_ns = _duration_ns(100, 350)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=_merge(root_attrs, biz.span_attrs({"dual_type.peer": "payments"})),
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 2_000_000
        for peer in chosen:
            d = _emit_external_client(
                session, tracer=tracer, parent_ctx=parent, peer=peer, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 1_000_000

    if txn.kind == "http":
        session.record_http_server(
            service_name=PRIMARY_SERVICE,
            duration_s=root_duration_ns / 1e9,
            method=txn.http_method or "POST",
            route=txn.http_route or "/api/v1/checkout",
            status_code=200,
        )
    return format_trace_id(trace_id)


def protocol_showcase(session: OtlpSession) -> str:
    """One span per major protocol family under a multi-protocol txn root."""
    biz = Biz()
    tracer = session.tracer(PRIMARY_SERVICE, pick_instance_id(PRIMARY_SERVICE))
    txn = pick_transaction()
    showcase_kinds = (
        "https",
        "http",
        "graphql",
        "soap",
        "websocket",
        "grpc",
        "connect_rpc",
        "dubbo",
        "jsonrpc",
        "java_rmi",
        "kafka",
        "rabbitmq",
        "sqs",
        "sns",
        "nats",
        "mqtt",
        "pulsar",
        "aws_s3",
        "aws_api",
        "other",
    )
    samples: list[PeerSpec] = []
    for k in showcase_kinds:
        matches = [p for p in catalog.PEERS if p.kind == k]
        if matches:
            samples.append(matches[0])

    age = _age_ns()
    root_start = time.time_ns() - age
    root_duration_ns = _duration_ns(200, 600)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=_merge(root_attrs, biz.span_attrs({"scenario": "protocol_showcase"})),
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 1_000_000
        for peer in samples:
            d = _emit_external_client(
                session, tracer=tracer, parent_ctx=parent, peer=peer, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 200_000

    return format_trace_id(trace_id)


def peer_naming_edges(session: OtlpSession) -> str:
    """peer_only / net_only / conflict / nameless in one request."""
    biz = Biz()
    tracer = session.tracer(PRIMARY_SERVICE, pick_instance_id(PRIMARY_SERVICE))
    txn = pick_transaction()
    edge_kinds = ("peer_only", "net_only", "conflict", "nameless")
    edges = [p for p in catalog.PEERS if p.kind in edge_kinds]
    age = _age_ns()
    root_start = time.time_ns() - age
    root_duration_ns = _duration_ns(60, 180)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=root_attrs,
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 1_000_000
        for peer in edges:
            d = _emit_external_client(
                session, tracer=tracer, parent_ctx=parent, peer=peer, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 500_000

    return format_trace_id(trace_id)


def database_heavy(session: OtlpSession) -> str:
    """Many DB CLIENT spans (db_system set) for Database tab."""
    biz = Biz()
    service = random.choice(
        ("demo-orders-service", PRIMARY_SERVICE, "demo-auth-service")
    )
    tracer = session.tracer(service, pick_instance_id(service))
    txn = pick_transaction()
    age = _age_ns()
    root_start = time.time_ns() - age
    n_db = random.randint(2, 5)
    ops = [pick_db_op() for _ in range(n_db)]
    total_ms = sum(random.uniform(*o.latency_ms) for o in ops) + 10
    root_duration_ns = _duration_ns(total_ms, total_ms + 30)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=root_attrs,
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 1_000_000
        for op in ops:
            d = _emit_db_client(
                session, tracer=tracer, parent_ctx=parent, op=op, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 300_000

    if txn.kind == "http":
        session.record_http_server(
            service_name=service,
            duration_s=root_duration_ns / 1e9,
            method=txn.http_method or "GET",
            route=txn.http_route or "/",
            status_code=200,
        )
    return format_trace_id(trace_id)


def no_db_schema_service_trace(session: OtlpSession) -> str:
    """demo-edge-bff: DB ops WITHOUT db.system (+ DB-looking HTTP peers).

    CLIENT spans still carry db.operation / db.statement / peer.service, but
    db.system and db.system.name are stripped — Database tab should soft-fail;
    External may pick them up depending on product rules.
    """
    biz = Biz()
    tracer = session.tracer(NO_DB_SCHEMA_SERVICE, pick_instance_id(NO_DB_SCHEMA_SERVICE))
    txn = pick_transaction()
    age = _age_ns()
    root_start = time.time_ns() - age

    # Real DB client shapes, but omit_db_system=True
    db_ops = [pick_db_op() for _ in range(random.randint(2, 4))]
    # Fake "db-looking" external peers without db_system
    fake_db_peers = [
        PeerSpec(
            name="postgres-lookalike",
            kind="http",
            host="postgres-lookalike.demo.internal",
            port=8080,
            weight=10,
            latency_ms=(10.0, 40.0),
            peer_service="postgres-lookalike",
            net_peer_name="postgres-lookalike.demo.internal",
            route="/query",
        ),
        PeerSpec(
            name="redis-proxy",
            kind="http",
            host="redis-proxy.demo.internal",
            port=8080,
            weight=10,
            latency_ms=(5.0, 20.0),
            peer_service="redis-proxy",
            net_peer_name="redis-proxy.demo.internal",
            route="/cache",
        ),
        pick_peer(),
    ]
    total_ms = sum(random.uniform(*o.latency_ms) for o in db_ops) + 20
    root_duration_ns = _duration_ns(total_ms, total_ms + 40)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=_merge(
            root_attrs,
            biz.span_attrs({"scenario": "no_db_system", "db.system.omitted": True}),
        ),
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 1_000_000
        for op in db_ops:
            d = _emit_db_client(
                session,
                tracer=tracer,
                parent_ctx=parent,
                op=op,
                biz=biz,
                start_ns=t,
                omit_db_system=True,
            )
            t += int(d * 1e9) + 300_000
        for peer in fake_db_peers:
            if peer.kind == "nameless":
                continue
            d = _emit_external_client(
                session, tracer=tracer, parent_ctx=parent, peer=peer, biz=biz, start_ns=t
            )
            t += int(d * 1e9) + 400_000

    return format_trace_id(trace_id)


def empty_external_service(session: OtlpSession) -> str:
    """SERVER/CONSUMER-only service — External tab should be empty for this service."""
    biz = Biz()
    tracer = session.tracer(
        EMPTY_EXTERNAL_SERVICE, pick_instance_id(EMPTY_EXTERNAL_SERVICE)
    )
    txn = pick_transaction()
    age = _age_ns()
    root_start = time.time_ns() - age
    root_duration_ns = _duration_ns(5, 25)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=root_attrs,
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        # INTERNAL only — must not pollute External
        parent = session.parent_context(
            root.get_span_context().trace_id, root.get_span_context().span_id
        )
        with _timed_span(
            tracer,
            "render_template",
            kind=SpanKind.INTERNAL,
            attributes=biz.span_attrs(),
            start_ns=root_start + 1_000_000,
            duration_ns=_duration_ns(1, 8),
            parent_ctx=parent,
        ):
            pass
        trace_id = root.get_span_context().trace_id

    if txn.kind == "http":
        session.record_http_server(
            service_name=EMPTY_EXTERNAL_SERVICE,
            duration_s=root_duration_ns / 1e9,
            method=txn.http_method or "GET",
            route=txn.http_route or "/static/{path}",
            status_code=200,
        )
    return format_trace_id(trace_id)


def gateway_mixed(session: OtlpSession) -> str:
    """Secondary traffic on demo-api-gateway for Overview multi-service view."""
    biz = Biz()
    service = "demo-api-gateway"
    tracer = session.tracer(service, pick_instance_id(service))
    txn = pick_transaction()
    age = _age_ns()
    root_start = time.time_ns() - age
    peer = pick_entity_type_peer()
    root_duration_ns = _duration_ns(30, 120)
    span_kind, root_attrs = _root_txn_attrs(txn, biz, status_code=200)

    with _timed_span(
        tracer,
        txn.name,
        kind=span_kind,
        attributes=root_attrs,
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        if peer.kind != "nameless":
            _emit_external_client(
                session,
                tracer=tracer,
                parent_ctx=parent,
                peer=peer,
                biz=biz,
                start_ns=root_start + 2_000_000,
            )
        if random.random() < 0.5:
            _emit_db_client(
                session,
                tracer=tracer,
                parent_ctx=parent,
                op=pick_db_op(),
                biz=biz,
                start_ns=root_start + 10_000_000,
            )

    return format_trace_id(trace_id)


def kafka_worker(session: OtlpSession) -> str:
    biz = Biz()
    service = "demo-notification-worker"
    tracer = session.tracer(service, pick_instance_id(service))
    age = _age_ns()
    root_start = time.time_ns() - age
    root_duration_ns = _duration_ns(40, 150)
    kafka_peers = [p for p in catalog.PEERS if p.kind == "kafka"]
    sqs_peers = [p for p in catalog.PEERS if p.kind == "sqs"]
    sns_peers = [p for p in catalog.PEERS if p.kind == "sns"]

    with _timed_span(
        tracer,
        "process orders.completed",
        kind=SpanKind.CONSUMER,
        attributes=_merge(
            attrs.messaging(
                system="kafka",
                destination="orders.completed",
                operation="process",
            ),
            biz.span_attrs(),
        ),
        start_ns=root_start,
        duration_ns=root_duration_ns,
    ) as root:
        trace_id = root.get_span_context().trace_id
        parent = session.parent_context(trace_id, root.get_span_context().span_id)
        t = root_start + 2_000_000
        _emit_db_client(
            session, tracer=tracer, parent_ctx=parent, op=pick_db_op(), biz=biz, start_ns=t
        )
        for pool in (kafka_peers, sqs_peers, sns_peers):
            if pool:
                t += 15_000_000
                _emit_external_client(
                    session,
                    tracer=tracer,
                    parent_ctx=parent,
                    peer=pool[-1],
                    biz=biz,
                    start_ns=t,
                )

    session.record_messaging_process(
        service_name=service,
        duration_s=root_duration_ns / 1e9,
        system="kafka",
        destination="orders.completed",
    )
    return format_trace_id(trace_id)


SCENARIOS: list[tuple[ScenarioFn, int]] = [
    (entity_type_demo, 28),
    (checkout_external_heavy, 26),
    (dual_type_peer_trace, 12),
    (protocol_showcase, 6),
    (peer_naming_edges, 3),
    (database_heavy, 10),
    (no_db_schema_service_trace, 10),  # demo-edge-bff: DB ops sans db.system
    (empty_external_service, 2),
    (gateway_mixed, 2),
    (kafka_worker, 2),
]


def pick_scenario() -> ScenarioFn:
    fns, weights = zip(*SCENARIOS)
    return random.choices(fns, weights=weights, k=1)[0]


def emit_random(session: OtlpSession) -> str:
    return pick_scenario()(session)
