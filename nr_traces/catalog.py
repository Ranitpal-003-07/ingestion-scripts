"""Prod-like entity catalogs for APM External / Database / Transactions tabs.

Targets (all >500 where noted):
  - TRANSACTION_ROUTES: server operation_name variety
  - HTTP_PEERS / SPECIAL_PEERS: External tab pagination + dual-type + edges
  - DB_OPERATIONS: Database tab (db_system set)
  - INSTANCE_IDS: service.instance.id cardinality
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

ENTITY_COUNT = 520

# ---------------------------------------------------------------------------
# Service roles
# ---------------------------------------------------------------------------

# Busy service for External-tab end-to-end walks.
PRIMARY_SERVICE = "demo-checkout"

# SERVER-only — External should be empty.
EMPTY_EXTERNAL_SERVICE = "demo-static-cdn"

# Emits outbound clients WITHOUT db_system (External only; can look DB-ish by name).
NO_DB_SCHEMA_SERVICE = "demo-edge-bff"

SERVICES = (
    PRIMARY_SERVICE,
    "demo-api-gateway",
    "demo-orders-service",
    "demo-inventory-service",
    "demo-payment-service",
    "demo-notification-worker",
    "demo-auth-service",
    NO_DB_SCHEMA_SERVICE,
    EMPTY_EXTERNAL_SERVICE,
)

SERVICE_META: dict[str, dict[str, str | int]] = {
    PRIMARY_SERVICE: {
        "version": "5.2.1",
        "host.name": "ip-10-4-12-20",
        "container.id": "chk-a1b2c3d4e5",
        "process.pid": 21001,
        "code.namespace": "checkout.http",
    },
    "demo-api-gateway": {
        "version": "2.8.1",
        "host.name": "ip-10-2-11-14",
        "container.id": "gw-7c9d4f2a1b",
        "process.pid": 18421,
        "code.namespace": "gateway.http",
    },
    "demo-orders-service": {
        "version": "1.19.4",
        "host.name": "ip-10-2-24-71",
        "container.id": "ord-3ae19c80d2",
        "process.pid": 22104,
        "code.namespace": "orders.api",
    },
    "demo-inventory-service": {
        "version": "1.6.0",
        "host.name": "ip-10-2-31-8",
        "container.id": "inv-91bb0e44c7",
        "process.pid": 19002,
        "code.namespace": "inventory.grpc",
    },
    "demo-payment-service": {
        "version": "3.2.7",
        "host.name": "ip-10-2-18-55",
        "container.id": "pay-55e1aa0193",
        "process.pid": 17650,
        "code.namespace": "payments.stripe",
    },
    "demo-notification-worker": {
        "version": "0.14.2",
        "host.name": "ip-10-2-41-12",
        "container.id": "ntf-c01d8aa4e6",
        "process.pid": 24011,
        "code.namespace": "notify.worker",
    },
    "demo-auth-service": {
        "version": "4.1.0",
        "host.name": "ip-10-2-9-33",
        "container.id": "auth-bb2188f091",
        "process.pid": 15808,
        "code.namespace": "auth.verify",
    },
    NO_DB_SCHEMA_SERVICE: {
        "version": "0.9.3",
        "host.name": "ip-10-5-1-9",
        "container.id": "bff-1122334455",
        "process.pid": 16040,
        "code.namespace": "edge.bff",
    },
    EMPTY_EXTERNAL_SERVICE: {
        "version": "1.0.0",
        "host.name": "ip-10-6-2-4",
        "container.id": "cdn-9988776655",
        "process.pid": 11002,
        "code.namespace": "cdn.static",
    },
}

INSTANCE_IDS: dict[str, tuple[str, ...]] = {
    svc: tuple(f"{svc}-i{n:04d}" for n in range(1, ENTITY_COUNT + 1))
    for svc in SERVICES
}


# ---------------------------------------------------------------------------
# Transactions (SERVER / CONSUMER operation_name) — multi-protocol
# ---------------------------------------------------------------------------

TxnKind = Literal[
    "http",
    "grpc",
    "graphql",
    "kafka",
    "rabbitmq",
    "sqs",
    "connect_rpc",
    "dubbo",
    "websocket",
    "other",
]

# Fixed mix for Transactions tab (non-HTTP must appear). Sum = 100.
TRANSACTION_TYPE_PERCENT: dict[str, int] = {
    "http": 35,
    "grpc": 25,
    "kafka": 15,
    "graphql": 10,
    "sqs": 5,
    "rabbitmq": 3,
    "connect_rpc": 3,
    "dubbo": 2,
    "websocket": 1,
    "other": 1,
}


@dataclass(frozen=True)
class TxnSpec:
    """Inbound transaction (SERVER/CONSUMER) for the Transactions tab."""

    name: str  # operation_name / span name
    kind: TxnKind
    weight: int = 10
    # HTTP
    http_method: str | None = None
    http_route: str | None = None
    http_scheme: str | None = None
    # RPC
    rpc_system: str | None = None
    rpc_service: str | None = None
    rpc_method: str | None = None
    # Messaging
    messaging_system: str | None = None
    messaging_destination: str | None = None
    messaging_operation: str | None = None
    # GraphQL
    graphql_operation: str | None = None
    graphql_type: str | None = None


def _build_transactions() -> tuple[TxnSpec, ...]:
    txns: list[TxnSpec] = []

    # --- HTTP (still majority, but not exclusive) ---
    http_named = (
        ("POST", "/api/v1/checkout"),
        ("GET", "/api/v1/checkout/{id}"),
        ("POST", "/api/v1/cart/items"),
        ("GET", "/api/v1/cart"),
        ("GET", "/api/v1/products/{id}"),
        ("GET", "/api/v1/search"),
        ("POST", "/api/v1/payments/charge"),
        ("GET", "/auth/verify"),
        ("POST", "/auth/session/refresh"),
        ("GET", "/api/v1/orders/{id}"),
        ("POST", "/api/v1/orders"),
        ("GET", "/web/home"),
        ("POST", "/web/checkout/submit"),
    )
    for method, route in http_named:
        txns.append(
            TxnSpec(
                name=f"{method} {route}",
                kind="http",
                weight=40,
                http_method=method,
                http_route=route,
                http_scheme="https",
            )
        )

    # --- gRPC SERVER transactions ---
    grpc_named = (
        ("checkout.CheckoutService", "CreateOrder"),
        ("checkout.CheckoutService", "GetCart"),
        ("inventory.InventoryService", "CheckStock"),
        ("inventory.InventoryService", "Reserve"),
        ("payments.PaymentService", "Charge"),
        ("payments.PaymentService", "Refund"),
        ("auth.AuthService", "VerifyToken"),
        ("shipping.ShippingService", "GetRates"),
        ("catalog.CatalogService", "Search"),
        ("orders.OrderService", "GetOrder"),
    )
    for svc, method in grpc_named:
        txns.append(
            TxnSpec(
                name=f"{svc}/{method}",
                kind="grpc",
                weight=35,
                rpc_system="grpc",
                rpc_service=svc,
                rpc_method=method,
            )
        )

    # --- GraphQL SERVER ---
    for op, typ in (
        ("Checkout", "mutation"),
        ("ProductSearch", "query"),
        ("OrderById", "query"),
        ("UpdateCart", "mutation"),
        ("Viewer", "query"),
    ):
        txns.append(
            TxnSpec(
                name=f"GraphQL {op}",
                kind="graphql",
                weight=25,
                http_method="POST",
                http_route="/graphql",
                http_scheme="https",
                graphql_operation=op,
                graphql_type=typ,
            )
        )

    # --- Messaging CONSUMER transactions ---
    for dest, system, kind in (
        ("orders.completed", "kafka", "kafka"),
        ("orders.created", "kafka", "kafka"),
        ("payment.captured", "kafka", "kafka"),
        ("email.send", "kafka", "kafka"),
        ("order.events", "rabbitmq", "rabbitmq"),
        ("fulfillment-jobs", "sqs", "sqs"),
        ("shipping-jobs", "sqs", "sqs"),
    ):
        txns.append(
            TxnSpec(
                name=f"process {dest}",
                kind=kind,  # type: ignore[arg-type]
                weight=30,
                messaging_system=system,
                messaging_destination=dest,
                messaging_operation="process",
            )
        )

    # --- Connect / Dubbo / WebSocket / other ---
    txns.extend(
        [
            TxnSpec(
                name="checkout.v1.CheckoutService/Submit",
                kind="connect_rpc",
                weight=15,
                rpc_system="connect_rpc",
                rpc_service="checkout.v1.CheckoutService",
                rpc_method="Submit",
            ),
            TxnSpec(
                name="com.demo.pricing.PricingService/quote",
                kind="dubbo",
                weight=12,
                rpc_system="apache_dubbo",
                rpc_service="com.demo.pricing.PricingService",
                rpc_method="quote",
            ),
            TxnSpec(
                name="WS /ws/checkout",
                kind="websocket",
                weight=10,
                http_method="GET",
                http_route="/ws/checkout",
                http_scheme="https",
                messaging_system="websocket",
                messaging_destination="/ws/checkout",
                messaging_operation="receive",
            ),
            TxnSpec(
                name="custom.handle",
                kind="other",
                weight=8,
            ),
        ]
    )

    # Bulk fill to ENTITY_COUNT with kind cycling so all types stay visible
    cycle: list[TxnKind] = [
        "http",
        "grpc",
        "kafka",
        "graphql",
        "sqs",
        "rabbitmq",
        "connect_rpc",
        "dubbo",
        "websocket",
        "other",
    ]
    resources = (
        "checkout",
        "orders",
        "payments",
        "inventory",
        "shipping",
        "auth",
        "catalog",
        "notify",
    )
    n = 0
    while len(txns) < ENTITY_COUNT:
        kind = cycle[n % len(cycle)]
        res = resources[n % len(resources)]
        if kind == "http":
            method = ("GET", "POST", "PUT", "DELETE")[n % 4]
            route = f"/api/v1/{res}/txn_{n:04d}"
            txns.append(
                TxnSpec(
                    name=f"{method} {route}",
                    kind="http",
                    weight=max(1, 15 - (n % 12)),
                    http_method=method,
                    http_route=route,
                    http_scheme="https",
                )
            )
        elif kind in ("grpc", "connect_rpc", "dubbo"):
            sys_map = {
                "grpc": "grpc",
                "connect_rpc": "connect_rpc",
                "dubbo": "apache_dubbo",
            }
            svc = f"{res}.{res.title()}Service"
            method = ("Get", "Create", "Update", "Delete")[n % 4]
            txns.append(
                TxnSpec(
                    name=f"{svc}/{method}",
                    kind=kind,
                    weight=max(1, 12 - (n % 10)),
                    rpc_system=sys_map[kind],
                    rpc_service=svc,
                    rpc_method=method,
                )
            )
        elif kind == "graphql":
            op = f"Op{n:04d}"
            txns.append(
                TxnSpec(
                    name=f"GraphQL {op}",
                    kind="graphql",
                    weight=max(1, 10 - (n % 8)),
                    http_method="POST",
                    http_route="/graphql",
                    http_scheme="https",
                    graphql_operation=op,
                    graphql_type="query" if n % 2 == 0 else "mutation",
                )
            )
        elif kind in ("kafka", "rabbitmq", "sqs"):
            dest = f"{res}.events.{n:04d}"
            txns.append(
                TxnSpec(
                    name=f"process {dest}",
                    kind=kind,
                    weight=max(1, 12 - (n % 9)),
                    messaging_system=kind,
                    messaging_destination=dest,
                    messaging_operation="process",
                )
            )
        elif kind == "websocket":
            route = f"/ws/{res}/{n:04d}"
            txns.append(
                TxnSpec(
                    name=f"WS {route}",
                    kind="websocket",
                    weight=max(1, 8 - (n % 6)),
                    http_method="GET",
                    http_route=route,
                    messaging_system="websocket",
                    messaging_destination=route,
                    messaging_operation="receive",
                )
            )
        else:
            txns.append(
                TxnSpec(
                    name=f"custom.{res}.handle_{n:04d}",
                    kind="other",
                    weight=max(1, 6 - (n % 5)),
                )
            )
        n += 1

    return tuple(txns[:ENTITY_COUNT])


TRANSACTIONS: tuple[TxnSpec, ...] = _build_transactions()
# Back-compat alias: string routes for any leftover callers
TRANSACTION_ROUTES: tuple[str, ...] = tuple(t.name for t in TRANSACTIONS)

_txn_lists: dict[str, list[TxnSpec]] = {}
for _t in TRANSACTIONS:
    _txn_lists.setdefault(_t.kind, []).append(_t)
_TXN_BY_KIND: dict[str, tuple[TxnSpec, ...]] = {
    k: tuple(v) for k, v in _txn_lists.items()
}

_TXN_TYPE_KEYS = tuple(TRANSACTION_TYPE_PERCENT.keys())
_TXN_TYPE_WEIGHTS = tuple(TRANSACTION_TYPE_PERCENT[k] for k in _TXN_TYPE_KEYS)


# ---------------------------------------------------------------------------
# External peers
# ---------------------------------------------------------------------------

PeerKind = Literal[
    # HTTP family
    "http",
    "https",
    "graphql",
    "soap",
    "websocket",
    # RPC family
    "grpc",
    "connect_rpc",
    "dubbo",
    "jsonrpc",
    "java_rmi",
    # Messaging
    "kafka",
    "rabbitmq",
    "sqs",
    "sns",
    "nats",
    "mqtt",
    "pulsar",
    # Cloud / AWS
    "aws_s3",
    "aws_api",
    # Naming / negative edges
    "peer_only",
    "net_only",
    "conflict",
    "nameless",
    "other",
]


@dataclass(frozen=True)
class PeerSpec:
    """One External (or edge) peer identity."""

    name: str  # display / peer.service preferred
    kind: PeerKind
    host: str
    port: int
    weight: int = 10
    latency_ms: tuple[float, float] = (8.0, 40.0)
    error_rate: float = 0.02
    http_error_rate: float = 0.03
    net_peer_name: str | None = None
    peer_service: str | None = None
    # HTTP / GraphQL / SOAP
    route: str | None = None
    scheme: str | None = None  # http | https | wss
    flavor: str | None = None  # 1.1 | 2.0 | 3.0
    graphql_operation: str | None = None
    graphql_type: str | None = None  # query | mutation | subscription
    soap_action: str | None = None
    # RPC
    rpc_system: str | None = None
    rpc_service: str | None = None
    rpc_method: str | None = None
    # Messaging
    messaging_system: str | None = None
    messaging_destination: str | None = None
    messaging_operation: str | None = None
    messaging_kind: str | None = None  # topic | queue
    # AWS
    aws_service: str | None = None
    aws_operation: str | None = None
    aws_region: str | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None


def _http_peer(
    name: str,
    *,
    kind: PeerKind = "https",
    weight: int = 10,
    latency_ms: tuple[float, float] = (8.0, 40.0),
    error_rate: float = 0.02,
    http_error_rate: float = 0.03,
    host: str | None = None,
    route: str | None = None,
    scheme: str | None = None,
    flavor: str | None = None,
) -> PeerSpec:
    host = host or f"{name}.demo.internal"
    if scheme is None:
        scheme = "https" if kind == "https" or host.endswith((".com", ".io", ".net")) else "http"
    port = 443 if scheme == "https" else 8080
    return PeerSpec(
        name=name,
        kind=kind,
        host=host,
        port=port,
        weight=weight,
        latency_ms=latency_ms,
        error_rate=error_rate,
        http_error_rate=http_error_rate,
        peer_service=name,
        net_peer_name=host,
        route=route or f"/v1/{name.replace('.', '/')}",
        scheme=scheme,
        flavor=flavor or ("2.0" if scheme == "https" else "1.1"),
    )


def _rpc_peer(
    name: str,
    *,
    kind: PeerKind,
    rpc_system: str,
    rpc_service: str,
    rpc_method: str,
    host: str | None = None,
    port: int = 50051,
    weight: int = 20,
    latency_ms: tuple[float, float] = (10.0, 60.0),
    error_rate: float = 0.03,
) -> PeerSpec:
    host = host or f"{name}-{kind}.demo.internal"
    return PeerSpec(
        name=name,
        kind=kind,
        host=host,
        port=port,
        weight=weight,
        latency_ms=latency_ms,
        error_rate=error_rate,
        peer_service=name,
        net_peer_name=host,
        rpc_system=rpc_system,
        rpc_service=rpc_service,
        rpc_method=rpc_method,
    )


def _msg_peer(
    name: str,
    *,
    kind: PeerKind,
    system: str,
    destination: str,
    operation: str = "publish",
    destination_kind: str = "topic",
    host: str | None = None,
    port: int = 9092,
    weight: int = 25,
    latency_ms: tuple[float, float] = (4.0, 30.0),
    region: str | None = None,
) -> PeerSpec:
    host = host or f"{system}.demo.internal"
    return PeerSpec(
        name=name,
        kind=kind,
        host=host,
        port=port,
        weight=weight,
        latency_ms=latency_ms,
        peer_service=name if name not in (destination, system) else system,
        net_peer_name=host,
        messaging_system=system,
        messaging_destination=destination,
        messaging_operation=operation,
        messaging_kind=destination_kind,
        aws_region=region,
    )


def _build_peers() -> tuple[PeerSpec, ...]:
    peers: list[PeerSpec] = []

    peers.extend(
        [
            # --- Dual-type: same peer_service, multiple protocols ---
            _http_peer(
                "payments",
                kind="https",
                weight=80,
                latency_ms=(40.0, 180.0),
                error_rate=0.04,
                http_error_rate=0.06,
                host="payments.demo.internal",
                route="/v1/charge",
                flavor="2.0",
            ),
            _rpc_peer(
                "payments",
                kind="grpc",
                rpc_system="grpc",
                rpc_service="payments.PaymentService",
                rpc_method="Charge",
                host="payments-grpc.demo.internal",
                weight=35,
                latency_ms=(15.0, 90.0),
            ),
            _rpc_peer(
                "payments",
                kind="connect_rpc",
                rpc_system="connect_rpc",
                rpc_service="payments.v1.PaymentService",
                rpc_method="Charge",
                host="payments-connect.demo.internal",
                port=8080,
                weight=18,
            ),
            _http_peer(
                "inventory",
                kind="http",
                weight=70,
                latency_ms=(10.0, 55.0),
                host="inventory.demo.internal",
                route="/stock/{sku}",
                scheme="http",
                flavor="1.1",
            ),
            _rpc_peer(
                "inventory",
                kind="grpc",
                rpc_system="grpc",
                rpc_service="inventory.InventoryService",
                rpc_method="CheckStock",
                host="inventory.demo.internal",
                weight=40,
            ),
            _http_peer(
                "shipping",
                kind="https",
                weight=55,
                latency_ms=(20.0, 120.0),
                host="shipping.demo.internal",
                route="/v1/rates",
            ),
            _msg_peer(
                "shipping",
                kind="sqs",
                system="sqs",
                destination="shipping-jobs",
                operation="publish",
                destination_kind="queue",
                host="sqs.us-east-1.amazonaws.com",
                port=443,
                weight=22,
                region="us-east-1",
            ),
            # Slow / fast ranks
            _http_peer(
                "fraud-check",
                kind="https",
                weight=45,
                latency_ms=(800.0, 2200.0),
                error_rate=0.08,
                http_error_rate=0.05,
                host="fraud.demo.internal",
                route="/v2/score",
            ),
            _http_peer(
                "recommendations",
                kind="https",
                weight=50,
                latency_ms=(600.0, 1800.0),
                host="recommend.demo-external.com",
                route="/v2/rank",
            ),
            _http_peer(
                "tax-engine",
                kind="https",
                weight=30,
                latency_ms=(500.0, 1500.0),
                host="tax.demo.internal",
                route="/v1/calculate",
            ),
            PeerSpec(
                name="legacy-erp",
                kind="soap",
                host="erp.legacy.demo.internal",
                port=8443,
                weight=25,
                latency_ms=(900.0, 2800.0),
                error_rate=0.12,
                http_error_rate=0.1,
                peer_service="legacy-erp",
                net_peer_name="erp.legacy.demo.internal",
                route="/soap/OrderService",
                scheme="https",
                soap_action="CreateOrder",
            ),
            _http_peer(
                "cdn-assets",
                kind="https",
                weight=60,
                latency_ms=(2.0, 12.0),
                host="cdn.demo.shop",
                route="/static/{path}",
                flavor="2.0",
            ),
            _http_peer(
                "config-service",
                kind="http",
                weight=40,
                latency_ms=(3.0, 15.0),
                host="config.demo.internal",
                route="/v1/flags",
                scheme="http",
            ),
            _http_peer(
                "partner-catalog",
                kind="https",
                weight=35,
                latency_ms=(30.0, 100.0),
                error_rate=0.0,
                http_error_rate=0.35,
                host="partner-catalog.external.com",
                route="/api/items",
            ),
            _http_peer(
                "webhook-dispatcher",
                kind="https",
                weight=20,
                latency_ms=(25.0, 80.0),
                error_rate=0.4,
                http_error_rate=0.05,
                host="webhooks.demo.internal",
                route="/dispatch",
            ),
            _http_peer(
                "stripe",
                kind="https",
                weight=65,
                latency_ms=(50.0, 200.0),
                host="api.stripe.com",
                route="/v1/payment_intents",
            ),
            _http_peer(
                "okta",
                kind="https",
                weight=30,
                latency_ms=(40.0, 150.0),
                host="idp.okta.com",
                route="/oauth2/v1/introspect",
            ),
            _http_peer(
                "twilio",
                kind="https",
                weight=20,
                latency_ms=(60.0, 220.0),
                host="api.twilio.com",
                route="/2010-04-01/Accounts/ACdemo/Messages.json",
            ),
            # GraphQL
            PeerSpec(
                name="catalog-graphql",
                kind="graphql",
                host="graphql.demo.internal",
                port=443,
                weight=40,
                latency_ms=(20.0, 120.0),
                peer_service="catalog-graphql",
                net_peer_name="graphql.demo.internal",
                route="/graphql",
                scheme="https",
                flavor="2.0",
                graphql_operation="ProductSearch",
                graphql_type="query",
            ),
            PeerSpec(
                name="checkout-graphql",
                kind="graphql",
                host="graphql.demo.internal",
                port=443,
                weight=28,
                latency_ms=(30.0, 150.0),
                error_rate=0.05,
                peer_service="checkout-graphql",
                net_peer_name="graphql.demo.internal",
                route="/graphql",
                scheme="https",
                graphql_operation="PlaceOrder",
                graphql_type="mutation",
            ),
            # WebSocket
            PeerSpec(
                name="realtime-updates",
                kind="websocket",
                host="ws.demo.shop",
                port=443,
                weight=30,
                latency_ms=(5.0, 40.0),
                peer_service="realtime-updates",
                net_peer_name="ws.demo.shop",
                route="/ws/checkout",
                scheme="wss",
            ),
            # More RPC systems
            _rpc_peer(
                "pricing",
                kind="dubbo",
                rpc_system="apache_dubbo",
                rpc_service="com.demo.pricing.PricingService",
                rpc_method="quote",
                host="dubbo-pricing.demo.internal",
                port=20880,
                weight=22,
            ),
            _rpc_peer(
                "loyalty",
                kind="jsonrpc",
                rpc_system="jsonrpc",
                rpc_service="loyalty",
                rpc_method="getPoints",
                host="jsonrpc-loyalty.demo.internal",
                port=8080,
                weight=18,
            ),
            _rpc_peer(
                "legacy-billing",
                kind="java_rmi",
                rpc_system="java_rmi",
                rpc_service="com.demo.billing.BillingRemote",
                rpc_method="invoice",
                host="rmi-billing.demo.internal",
                port=1099,
                weight=12,
                latency_ms=(80.0, 400.0),
            ),
            # Messaging systems
            _msg_peer(
                "orders.completed",
                kind="kafka",
                system="kafka",
                destination="orders.completed",
                host="kafka-orders.demo.internal",
                port=9092,
                weight=40,
            ),
            _msg_peer(
                "email.send",
                kind="kafka",
                system="kafka",
                destination="email.send",
                host="kafka-orders.demo.internal",
                weight=25,
            ),
            _msg_peer(
                "order-events",
                kind="rabbitmq",
                system="rabbitmq",
                destination="order.events",
                destination_kind="queue",
                host="rabbitmq.demo.internal",
                port=5672,
                weight=28,
            ),
            _msg_peer(
                "fulfillment-jobs",
                kind="sqs",
                system="sqs",
                destination="fulfillment-jobs",
                destination_kind="queue",
                host="sqs.us-east-1.amazonaws.com",
                port=443,
                weight=30,
                region="us-east-1",
            ),
            _msg_peer(
                "order-notifications",
                kind="sns",
                system="sns",
                destination="order-notifications",
                host="sns.us-east-1.amazonaws.com",
                port=443,
                weight=20,
                region="us-east-1",
            ),
            _msg_peer(
                "checkout.events",
                kind="nats",
                system="nats",
                destination="checkout.events",
                host="nats.demo.internal",
                port=4222,
                weight=18,
            ),
            _msg_peer(
                "device/telemetry",
                kind="mqtt",
                system="mqtt",
                destination="device/telemetry",
                host="mqtt.demo.internal",
                port=1883,
                weight=14,
            ),
            _msg_peer(
                "persistent.orders",
                kind="pulsar",
                system="pulsar",
                destination="persistent://public/default/orders",
                host="pulsar.demo.internal",
                port=6650,
                weight=16,
            ),
            # AWS APIs
            PeerSpec(
                name="aws.s3",
                kind="aws_s3",
                host="demo-order-receipts.s3.us-east-1.amazonaws.com",
                port=443,
                weight=35,
                latency_ms=(15.0, 80.0),
                peer_service="aws.s3",
                net_peer_name="demo-order-receipts.s3.us-east-1.amazonaws.com",
                aws_service="s3",
                aws_operation="PutObject",
                aws_region="us-east-1",
                s3_bucket="demo-order-receipts",
                s3_key="receipts/{order_id}.pdf",
            ),
            PeerSpec(
                name="aws.dynamodb",
                kind="aws_api",
                host="dynamodb.us-east-1.amazonaws.com",
                port=443,
                weight=28,
                latency_ms=(8.0, 45.0),
                peer_service="aws.dynamodb",
                net_peer_name="dynamodb.us-east-1.amazonaws.com",
                aws_service="dynamodb",
                aws_operation="GetItem",
                aws_region="us-east-1",
            ),
            PeerSpec(
                name="aws.lambda",
                kind="aws_api",
                host="lambda.us-east-1.amazonaws.com",
                port=443,
                weight=18,
                latency_ms=(40.0, 250.0),
                peer_service="aws.lambda",
                net_peer_name="lambda.us-east-1.amazonaws.com",
                aws_service="lambda",
                aws_operation="Invoke",
                aws_region="us-east-1",
            ),
            # Naming edges
            PeerSpec(
                name="peer-only-svc",
                kind="peer_only",
                host="peer-only.demo.internal",
                port=8080,
                weight=15,
                latency_ms=(12.0, 40.0),
                peer_service="peer-only-svc",
                net_peer_name=None,
                route="/v1/ping",
                scheme="http",
            ),
            PeerSpec(
                name="net-only-host",
                kind="net_only",
                host="net-only-host.demo.internal",
                port=8080,
                weight=15,
                latency_ms=(12.0, 40.0),
                peer_service=None,
                net_peer_name="net-only-host.demo.internal",
                route="/v1/ping",
                scheme="http",
            ),
            PeerSpec(
                name="conflict-peer",
                kind="conflict",
                host="conflict-host.demo.internal",
                port=8080,
                weight=18,
                latency_ms=(15.0, 50.0),
                peer_service="conflict-peer",
                net_peer_name="conflict-OTHER-name.demo.internal",
                route="/v1/conflict",
                scheme="http",
            ),
            PeerSpec(
                name="",
                kind="nameless",
                host="",
                port=0,
                weight=5,
                latency_ms=(5.0, 20.0),
                peer_service=None,
                net_peer_name=None,
            ),
            PeerSpec(
                name="custom-protocol-gw",
                kind="other",
                host="custom-gw.demo.internal",
                port=9443,
                weight=12,
                latency_ms=(20.0, 70.0),
                peer_service="custom-protocol-gw",
                net_peer_name="custom-gw.demo.internal",
            ),
        ]
    )

    # Bulk peers cycle protocols for pagination + entity_type group-by
    protocol_cycle: list[PeerKind] = [
        "https",
        "http",
        "grpc",
        "connect_rpc",
        "graphql",
        "kafka",
        "rabbitmq",
        "sqs",
        "sns",
        "nats",
        "mqtt",
        "pulsar",
        "dubbo",
        "jsonrpc",
        "java_rmi",
        "aws_api",
        "aws_s3",
        "websocket",
        "soap",
        "other",
    ]
    domains = (
        "demo.internal",
        "svc.cluster.local",
        "partner.external.com",
        "vendor.io",
        "api.partner.net",
    )
    while len(peers) < ENTITY_COUNT:
        i = len(peers)
        kind = protocol_cycle[i % len(protocol_cycle)]
        domain = domains[i % len(domains)]
        name = f"ext-peer-{i:04d}"
        weight = max(1, int(40 / (1 + (i % 50))))
        latency = (
            (700.0, 1600.0)
            if i % 47 == 0
            else ((3.0, 18.0) if i % 11 == 0 else (10.0, 80.0))
        )
        host = f"{name}.{domain}"
        if kind in ("https", "http"):
            peers.append(
                _http_peer(
                    name,
                    kind=kind,
                    weight=weight,
                    latency_ms=latency,
                    host=host,
                    route=f"/api/{name}/call",
                    scheme="https" if kind == "https" else "http",
                    error_rate=0.01 if i % 9 else 0.05,
                    http_error_rate=0.02 if i % 7 else 0.08,
                )
            )
        elif kind in ("grpc", "connect_rpc", "dubbo", "jsonrpc", "java_rmi"):
            sys_map = {
                "grpc": "grpc",
                "connect_rpc": "connect_rpc",
                "dubbo": "apache_dubbo",
                "jsonrpc": "jsonrpc",
                "java_rmi": "java_rmi",
            }
            ports = {"grpc": 50051, "connect_rpc": 8080, "dubbo": 20880, "jsonrpc": 8080, "java_rmi": 1099}
            peers.append(
                _rpc_peer(
                    name,
                    kind=kind,
                    rpc_system=sys_map[kind],
                    rpc_service=f"{name}.Service",
                    rpc_method=random.choice(("Get", "Put", "Call", "Execute")),
                    host=host,
                    port=ports[kind],
                    weight=weight,
                    latency_ms=latency,
                )
            )
        elif kind in ("kafka", "rabbitmq", "sqs", "sns", "nats", "mqtt", "pulsar"):
            ports = {
                "kafka": 9092,
                "rabbitmq": 5672,
                "sqs": 443,
                "sns": 443,
                "nats": 4222,
                "mqtt": 1883,
                "pulsar": 6650,
            }
            peers.append(
                _msg_peer(
                    name,
                    kind=kind,
                    system=kind,
                    destination=f"{name}.events",
                    host=host if kind not in ("sqs", "sns") else f"{kind}.us-east-1.amazonaws.com",
                    port=ports[kind],
                    weight=weight,
                    latency_ms=latency,
                    region="us-east-1" if kind in ("sqs", "sns") else None,
                    destination_kind="queue" if kind in ("sqs", "rabbitmq") else "topic",
                )
            )
        elif kind == "graphql":
            peers.append(
                PeerSpec(
                    name=name,
                    kind="graphql",
                    host=host,
                    port=443,
                    weight=weight,
                    latency_ms=latency,
                    peer_service=name,
                    net_peer_name=host,
                    route="/graphql",
                    scheme="https",
                    graphql_operation=f"Op{i}",
                    graphql_type=random.choice(("query", "mutation")),
                )
            )
        elif kind == "websocket":
            peers.append(
                PeerSpec(
                    name=name,
                    kind="websocket",
                    host=host,
                    port=443,
                    weight=weight,
                    latency_ms=latency,
                    peer_service=name,
                    net_peer_name=host,
                    route=f"/ws/{name}",
                    scheme="wss",
                )
            )
        elif kind == "soap":
            peers.append(
                PeerSpec(
                    name=name,
                    kind="soap",
                    host=host,
                    port=8443,
                    weight=weight,
                    latency_ms=latency,
                    peer_service=name,
                    net_peer_name=host,
                    route="/soap",
                    scheme="https",
                    soap_action=f"Action{i}",
                )
            )
        elif kind == "aws_s3":
            peers.append(
                PeerSpec(
                    name=f"aws.s3-{i:04d}",
                    kind="aws_s3",
                    host=f"bucket-{i:04d}.s3.us-east-1.amazonaws.com",
                    port=443,
                    weight=weight,
                    latency_ms=latency,
                    peer_service="aws.s3",
                    net_peer_name=f"bucket-{i:04d}.s3.us-east-1.amazonaws.com",
                    aws_service="s3",
                    aws_operation=random.choice(("PutObject", "GetObject", "HeadObject")),
                    aws_region="us-east-1",
                    s3_bucket=f"demo-bucket-{i:04d}",
                    s3_key=f"objects/{i}.bin",
                )
            )
        elif kind == "aws_api":
            svc = random.choice(("dynamodb", "lambda", "sns", "sqs", "kinesis"))
            peers.append(
                PeerSpec(
                    name=f"aws.{svc}-{i:04d}",
                    kind="aws_api",
                    host=f"{svc}.us-east-1.amazonaws.com",
                    port=443,
                    weight=weight,
                    latency_ms=latency,
                    peer_service=f"aws.{svc}",
                    net_peer_name=f"{svc}.us-east-1.amazonaws.com",
                    aws_service=svc,
                    aws_operation=random.choice(("GetItem", "PutItem", "Invoke", "Publish")),
                    aws_region="us-east-1",
                )
            )
        else:
            peers.append(
                PeerSpec(
                    name=name,
                    kind="other",
                    host=host,
                    port=9443,
                    weight=weight,
                    latency_ms=latency,
                    peer_service=name,
                    net_peer_name=host,
                )
            )

    return tuple(peers[:ENTITY_COUNT])


PEERS: tuple[PeerSpec, ...] = _build_peers()
PEER_WEIGHTS: tuple[int, ...] = tuple(p.weight for p in PEERS)

# Dual-type peer names (table shows 2+ rows; chart may merge by name)
DUAL_TYPE_PEERS = ("payments", "inventory", "shipping")


# ---------------------------------------------------------------------------
# APM External entity_type recipes (fixed mix)
# ---------------------------------------------------------------------------

# Fixed percentages for External client spans — must sum to 100.
# Used by pick_entity_type_peer() so http / grpc / other ratios stay stable.
ENTITY_TYPE_PERCENT: dict[str, int] = {
    "http": 40,
    "grpc": 25,
    "kafka": 15,
    "graphql_http": 10,
    "other": 10,
}

# Canonical recipe peers for discovery + dual-type payments.
ENTITY_TYPE_RECIPES: dict[str, PeerSpec] = {
    "http": PeerSpec(
        name="payments",
        kind="http",
        host="payments.demo.internal",
        port=8080,
        weight=100,
        latency_ms=(20.0, 80.0),
        error_rate=0.05,
        http_error_rate=0.08,
        peer_service="payments",
        net_peer_name="payments.demo.internal",
        route="/charge",
        scheme="http",
        flavor="1.1",
    ),
    "http_slow": PeerSpec(
        name="fraud-check",
        kind="https",
        host="fraud.demo.internal",
        port=443,
        weight=100,
        latency_ms=(900.0, 2400.0),
        error_rate=0.06,
        http_error_rate=0.04,
        peer_service="fraud-check",
        net_peer_name="fraud.demo.internal",
        route="/v2/score",
        scheme="https",
        flavor="2.0",
    ),
    "http_fast": PeerSpec(
        name="shipping",
        kind="https",
        host="shipping.demo.internal",
        port=443,
        weight=100,
        latency_ms=(5.0, 25.0),
        peer_service="shipping",
        net_peer_name="shipping.demo.internal",
        route="/v1/rates",
        scheme="https",
        flavor="2.0",
    ),
    "http_errors": PeerSpec(
        name="partner-catalog",
        kind="https",
        host="partner-catalog.external.com",
        port=443,
        weight=100,
        latency_ms=(30.0, 100.0),
        error_rate=0.0,
        http_error_rate=0.4,
        peer_service="partner-catalog",
        net_peer_name="partner-catalog.external.com",
        route="/api/items",
        scheme="https",
    ),
    "grpc": PeerSpec(
        name="inventory",
        kind="grpc",
        host="inventory.demo.internal",
        port=50051,
        weight=100,
        latency_ms=(8.0, 45.0),
        error_rate=0.06,
        peer_service="inventory",
        net_peer_name="inventory.demo.internal",
        rpc_system="grpc",
        rpc_service="inventory.InventoryService",
        rpc_method="CheckStock",
    ),
    "grpc_payments": PeerSpec(
        name="payments",
        kind="grpc",
        host="payments-grpc.demo.internal",
        port=50051,
        weight=100,
        latency_ms=(15.0, 90.0),
        error_rate=0.05,
        peer_service="payments",
        net_peer_name="payments-grpc.demo.internal",
        rpc_system="grpc",
        rpc_service="payments.PaymentService",
        rpc_method="Charge",
    ),
    "kafka": PeerSpec(
        name="orders-bus",
        kind="kafka",
        host="kafka-orders.demo.internal",
        port=9092,
        weight=100,
        latency_ms=(4.0, 28.0),
        peer_service="orders-bus",
        net_peer_name="kafka-orders.demo.internal",
        messaging_system="kafka",
        messaging_destination="orders.completed",
        messaging_operation="publish",
        messaging_kind="topic",
    ),
    "graphql_http": PeerSpec(
        name="catalog-graphql",
        kind="graphql",
        host="graphql.demo.internal",
        port=443,
        weight=100,
        latency_ms=(20.0, 100.0),
        error_rate=0.04,
        http_error_rate=0.03,
        peer_service="catalog-graphql",
        net_peer_name="graphql.demo.internal",
        route="/graphql",
        scheme="https",
        flavor="2.0",
        graphql_operation="ProductSearch",
        graphql_type="query",
    ),
    "other": PeerSpec(
        name="mystery-peer",
        kind="other",
        host="mystery.demo.internal",
        port=9443,
        weight=100,
        latency_ms=(15.0, 60.0),
        peer_service="mystery-peer",
        net_peer_name="mystery.demo.internal",
    ),
}

_ENTITY_TYPE_KEYS = tuple(ENTITY_TYPE_PERCENT.keys())
_ENTITY_TYPE_WEIGHTS = tuple(ENTITY_TYPE_PERCENT[k] for k in _ENTITY_TYPE_KEYS)

# Pool per entity_type for variety while keeping fixed type mix.
_ENTITY_TYPE_POOLS: dict[str, tuple[PeerSpec, ...]] = {
    "http": (
        ENTITY_TYPE_RECIPES["http"],
        ENTITY_TYPE_RECIPES["http_slow"],
        ENTITY_TYPE_RECIPES["http_fast"],
        ENTITY_TYPE_RECIPES["http_errors"],
        *(p for p in PEERS if p.kind in ("http", "https") and p.peer_service not in (None, "")),
    ),
    "grpc": (
        ENTITY_TYPE_RECIPES["grpc"],
        ENTITY_TYPE_RECIPES["grpc_payments"],
        *(p for p in PEERS if p.kind == "grpc"),
    ),
    "kafka": (
        ENTITY_TYPE_RECIPES["kafka"],
        *(p for p in PEERS if p.kind == "kafka"),
    ),
    "graphql_http": (
        ENTITY_TYPE_RECIPES["graphql_http"],
        *(p for p in PEERS if p.kind == "graphql"),
    ),
    "other": (
        ENTITY_TYPE_RECIPES["other"],
        *(p for p in PEERS if p.kind == "other"),
    ),
}


def pick_entity_type() -> str:
    """Pick entity_type with fixed percentages (http/grpc/kafka/graphql_http/other)."""
    return random.choices(_ENTITY_TYPE_KEYS, weights=_ENTITY_TYPE_WEIGHTS, k=1)[0]


def pick_entity_type_peer(entity_type: str | None = None) -> PeerSpec:
    """Pick a peer for a fixed entity_type bucket."""
    et = entity_type or pick_entity_type()
    pool = _ENTITY_TYPE_POOLS.get(et) or (ENTITY_TYPE_RECIPES["http"],)
    # Within http: bias recipe peers (payments, slow, fast, errors)
    if et == "http":
        weights = [40, 25, 20, 15] + [1] * max(0, len(pool) - 4)
        weights = weights[: len(pool)]
        return random.choices(pool, weights=weights, k=1)[0]
    if et == "grpc":
        # ~50% inventory recipe, ~30% payments dual-type, rest bulk
        weights = [50, 30] + [2] * max(0, len(pool) - 2)
        weights = weights[: len(pool)]
        return random.choices(pool, weights=weights, k=1)[0]
    return random.choice(pool)



# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DbOp:
    system: str
    operation: str
    table: str
    statement: str
    peer: str
    db_name: str
    weight: int = 10
    latency_ms: tuple[float, float] = (3.0, 25.0)
    error_rate: float = 0.01


def _build_db_ops() -> tuple[DbOp, ...]:
    ops: list[DbOp] = []
    named = (
        DbOp(
            "postgresql",
            "SELECT",
            "orders",
            "SELECT * FROM orders WHERE id = $1",
            "postgresql-orders.demo.internal",
            "orders_db",
            weight=60,
            latency_ms=(4.0, 30.0),
        ),
        DbOp(
            "postgresql",
            "INSERT",
            "orders",
            "INSERT INTO orders (id, customer_id) VALUES ($1, $2)",
            "postgresql-orders.demo.internal",
            "orders_db",
            weight=40,
            latency_ms=(5.0, 35.0),
        ),
        DbOp(
            "postgresql",
            "UPDATE",
            "orders",
            "UPDATE orders SET status = $1 WHERE id = $2",
            "postgresql-orders.demo.internal",
            "orders_db",
            weight=30,
        ),
        DbOp(
            "postgresql",
            "SELECT",
            "customers",
            "SELECT id, email FROM customers WHERE id = $1",
            "postgresql-orders.demo.internal",
            "orders_db",
            weight=45,
        ),
        DbOp(
            "postgresql",
            "SELECT",
            "order_items",
            "SELECT * FROM order_items WHERE order_id = $1",
            "postgresql-orders.demo.internal",
            "orders_db",
            weight=35,
        ),
        DbOp(
            "mysql",
            "SELECT",
            "products",
            "SELECT id, name, price_cents FROM products WHERE id = ?",
            "mysql-catalog.demo.internal",
            "products_db",
            weight=50,
            latency_ms=(3.0, 22.0),
        ),
        DbOp(
            "mongodb",
            "find",
            "facets",
            "db.facets.find({q: ?})",
            "mongodb-catalog.demo.internal",
            "catalog",
            weight=25,
        ),
        DbOp(
            "mongodb",
            "aggregate",
            "facets",
            "db.facets.aggregate([{$match:{q:?}}])",
            "mongodb-catalog.demo.internal",
            "catalog",
            weight=20,
        ),
        DbOp(
            "redis",
            "GET",
            "session",
            "GET session:{token}",
            "redis-auth-cache.demo.internal",
            "session",
            weight=70,
            latency_ms=(1.0, 8.0),
        ),
        DbOp(
            "redis",
            "SET",
            "cart",
            "SET cart:{id} {payload}",
            "redis-cart.demo.internal",
            "cart",
            weight=40,
            latency_ms=(1.0, 6.0),
        ),
        DbOp(
            "redis",
            "GET",
            "inventory",
            "GET inv:{sku}",
            "redis-inventory.demo.internal",
            "inventory",
            weight=35,
            latency_ms=(1.0, 5.0),
        ),
        DbOp(
            "elasticsearch",
            "search",
            "products",
            '{"query":{"match":{"name":"?"}}}',
            "es-search.demo.internal",
            "products",
            weight=30,
            latency_ms=(15.0, 80.0),
        ),
        DbOp(
            "postgresql",
            "INSERT",
            "orders",
            "INSERT INTO orders (id, sku) VALUES ($1, $2)",
            "postgresql-orders.demo.internal",
            "orders_db",
            weight=8,
            error_rate=0.25,
            latency_ms=(8.0, 40.0),
        ),
    )
    ops.extend(named)

    systems = (
        ("postgresql", "orders_db", "postgresql-orders.demo.internal", ("SELECT", "INSERT", "UPDATE", "DELETE")),
        ("mysql", "products_db", "mysql-catalog.demo.internal", ("SELECT", "INSERT", "UPDATE")),
        ("mongodb", "catalog", "mongodb-catalog.demo.internal", ("find", "insert", "update", "aggregate")),
        ("redis", "cache", "redis-cluster.demo.internal", ("GET", "SET", "DEL", "HGET", "ZADD")),
    )
    tables = (
        "orders",
        "customers",
        "payments",
        "shipments",
        "inventory",
        "products",
        "reviews",
        "sessions",
        "carts",
        "audit_log",
        "price_book",
        "coupons",
        "warehouses",
        "fulfillments",
        "returns",
    )
    n = 0
    while len(ops) < ENTITY_COUNT:
        system, db_name, peer, op_list = systems[n % len(systems)]
        op = op_list[n % len(op_list)]
        table = tables[n % len(tables)]
        ops.append(
            DbOp(
                system=system,
                operation=op,
                table=f"{table}_{n % 40:02d}",
                statement=f"{op} {table} /* op_{n:04d} */",
                peer=peer,
                db_name=db_name,
                weight=max(1, 20 - (n % 20)),
                latency_ms=(2.0, 40.0) if system != "redis" else (0.5, 6.0),
                error_rate=0.02 if n % 31 == 0 else 0.005,
            )
        )
        n += 1
    return tuple(ops[:ENTITY_COUNT])


DB_OPERATIONS: tuple[DbOp, ...] = _build_db_ops()
DB_WEIGHTS: tuple[int, ...] = tuple(d.weight for d in DB_OPERATIONS)


def pick_peer() -> PeerSpec:
    return random.choices(PEERS, weights=PEER_WEIGHTS, k=1)[0]


def pick_db_op() -> DbOp:
    return random.choices(DB_OPERATIONS, weights=DB_WEIGHTS, k=1)[0]


def pick_transaction_type() -> str:
    return random.choices(_TXN_TYPE_KEYS, weights=_TXN_TYPE_WEIGHTS, k=1)[0]


def pick_transaction(kind: str | None = None) -> TxnSpec:
    """Pick a transaction with fixed protocol mix (http/grpc/kafka/…)."""
    k = kind or pick_transaction_type()
    pool = _TXN_BY_KIND.get(k) or _TXN_BY_KIND.get("http") or TRANSACTIONS
    return random.choice(pool)


def pick_transaction_route() -> str:
    """Back-compat: return operation_name string."""
    return pick_transaction().name


def pick_instance_id(service: str) -> str:
    ids = INSTANCE_IDS[service]
    idx = min(int(random.paretovariate(1.15)) - 1, len(ids) - 1)
    return ids[max(0, idx)]


def method_and_route(txn: str) -> tuple[str, str]:
    parts = txn.split(" ", 1)
    if len(parts) == 2 and parts[0] in (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    ):
        return parts[0], parts[1]
    return "GET", txn
