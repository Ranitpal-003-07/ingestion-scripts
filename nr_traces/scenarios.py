"""Synthetic trace scenarios for New Relic APM coverage."""

from __future__ import annotations

import random
import time
from typing import Callable

from opentelemetry.trace import SpanKind, Status, StatusCode

from nr_traces.ids import (
    format_trace_id,
    random_customer_id,
    random_order_id,
    random_sku,
)
from nr_traces.otlp import OtlpSession

# (emitter, weight)
ScenarioFn = Callable[[OtlpSession], str]


def _sleep_ms(low_ms: float, high_ms: float) -> float:
    duration_s = random.uniform(low_ms, high_ms) / 1000.0
    time.sleep(duration_s)
    return duration_s


def _custom_attrs(span, **extra: str) -> None:
    span.set_attribute("customer.id", random_customer_id())
    span.set_attribute("order.id", random_order_id())
    for key, value in extra.items():
        span.set_attribute(key, value)


def checkout_happy_path(session: OtlpSession) -> str:
    sku = random_sku()
    total_duration = 0.0

    gateway_tracer = session.tracer("demo-api-gateway")
    orders_tracer = session.tracer("demo-orders-service")
    payment_tracer = session.tracer("demo-payment-service")

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        gateway_span_id = gateway_span.get_span_context().span_id
        gateway_span.set_attribute("http.request.method", "POST")
        gateway_span.set_attribute("http.route", "/api/v1/checkout")
        gateway_span.set_attribute("http.response.status_code", 200)
        gateway_span.set_attribute("transaction.name", "WebTransaction/Action/checkout")
        _custom_attrs(gateway_span)
        gateway_span.set_attribute("region", random.choice(["us-east", "eu-west", "ap-south"]))

        orders_ctx = session.parent_context(trace_id, gateway_span_id)
        with orders_tracer.start_as_current_span(
            "POST /internal/orders",
            context=orders_ctx,
            kind=SpanKind.SERVER,
        ) as orders_span:
            orders_span_id = orders_span.get_span_context().span_id
            orders_span.set_attribute("http.request.method", "POST")
            orders_span.set_attribute("http.route", "/internal/orders")
            orders_span.set_attribute("http.response.status_code", 200)

            validate_ctx = session.parent_context(trace_id, orders_span_id)
            with orders_tracer.start_as_current_span(
                "validate_cart",
                context=validate_ctx,
                kind=SpanKind.INTERNAL,
            ):
                total_duration += _sleep_ms(2, 15)

            db_ctx = session.parent_context(trace_id, orders_span_id)
            with orders_tracer.start_as_current_span(
                "SELECT orders",
                context=db_ctx,
                kind=SpanKind.CLIENT,
                attributes={
                    "db.system": "postgresql",
                    "db.operation": "SELECT",
                    "db.name": "orders_db",
                    "db.collection": "orders",
                    "db.statement": "SELECT * FROM orders WHERE id = $1",
                    "peer.service": "postgresql-orders",
                },
            ):
                total_duration += _sleep_ms(5, 25)

            inv_ctx = session.parent_context(trace_id, orders_span_id)
            inv_duration = _sleep_ms(10, 40)
            with orders_tracer.start_as_current_span(
                "GET inventory",
                context=inv_ctx,
                kind=SpanKind.CLIENT,
                attributes={
                    "http.method": "GET",
                    "http.url": f"http://inventory:8080/stock/{sku}",
                    "server.address": "inventory",
                    "server.port": 8080,
                    "http.response.status_code": 200,
                    "peer.service": "demo-inventory-service",
                },
            ):
                pass
            session.record_http_client(
                service_name="demo-orders-service",
                duration_s=inv_duration,
                method="GET",
                url=f"http://inventory:8080/stock/{sku}",
                status_code=200,
            )
            total_duration += inv_duration

            pay_ctx = session.parent_context(trace_id, orders_span_id)
            pay_duration = _sleep_ms(15, 50)
            with payment_tracer.start_as_current_span(
                "POST charge",
                context=pay_ctx,
                kind=SpanKind.CLIENT,
                attributes={
                    "http.method": "POST",
                    "http.url": "https://payments.example.com/charge",
                    "server.address": "payments.example.com",
                    "http.response.status_code": 200,
                },
            ):
                pass
            session.record_http_client(
                service_name="demo-payment-service",
                duration_s=pay_duration,
                method="POST",
                url="https://payments.example.com/charge",
                status_code=200,
            )
            total_duration += pay_duration

            total_duration += _sleep_ms(20, 60)

        total_duration += _sleep_ms(30, 80)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="POST",
        route="/api/v1/checkout",
        status_code=200,
    )
    return format_trace_id(trace_id)


def checkout_payment_failure(session: OtlpSession) -> str:
    gateway_tracer = session.tracer("demo-api-gateway")
    orders_tracer = session.tracer("demo-orders-service")
    payment_tracer = session.tracer("demo-payment-service")
    total_duration = 0.0
    status_code = random.choice([500, 502])

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        gateway_span_id = gateway_span.get_span_context().span_id
        gateway_span.set_attribute("http.request.method", "POST")
        gateway_span.set_attribute("http.route", "/api/v1/checkout")
        gateway_span.set_attribute("transaction.name", "WebTransaction/Action/checkout")
        _custom_attrs(gateway_span)

        orders_ctx = session.parent_context(trace_id, gateway_span_id)
        with orders_tracer.start_as_current_span(
            "POST /internal/orders",
            context=orders_ctx,
            kind=SpanKind.SERVER,
        ) as orders_span:
            orders_span_id = orders_span.get_span_context().span_id
            orders_span.set_attribute("http.response.status_code", status_code)

            pay_ctx = session.parent_context(trace_id, orders_span_id)
            pay_duration = _sleep_ms(20, 60)
            with payment_tracer.start_as_current_span(
                "POST charge",
                context=pay_ctx,
                kind=SpanKind.CLIENT,
                attributes={
                    "http.method": "POST",
                    "http.url": "https://payments.example.com/charge",
                    "server.address": "payments.example.com",
                    "http.response.status_code": 502,
                },
            ) as pay_span:
                pay_span.set_status(Status(StatusCode.ERROR, "Payment gateway unavailable"))
                pay_span.record_exception(
                    RuntimeError("Payment gateway returned 502 Bad Gateway")
                )
            session.record_http_client(
                service_name="demo-payment-service",
                duration_s=pay_duration,
                method="POST",
                url="https://payments.example.com/charge",
                status_code=502,
            )
            total_duration += pay_duration

            orders_span.set_status(Status(StatusCode.ERROR, "checkout failed"))
            total_duration += _sleep_ms(10, 30)

        gateway_span.set_attribute("http.response.status_code", status_code)
        gateway_span.set_status(Status(StatusCode.ERROR, "checkout failed"))
        total_duration += _sleep_ms(40, 100)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="POST",
        route="/api/v1/checkout",
        status_code=status_code,
    )
    return format_trace_id(trace_id)


def auth_slow_trace(session: OtlpSession) -> str:
    auth_tracer = session.tracer("demo-auth-service")
    total_duration = 0.0

    with auth_tracer.start_as_current_span(
        "GET /auth/verify",
        kind=SpanKind.SERVER,
        attributes={
            "http.request.method": "GET",
            "http.route": "/auth/verify",
            "http.response.status_code": 200,
            "transaction.name": "WebTransaction/Action/auth_verify",
        },
    ) as auth_span:
        trace_id = auth_span.get_span_context().trace_id
        auth_span_id = auth_span.get_span_context().span_id
        _custom_attrs(auth_span)
        auth_span.set_attribute("feature.flag", "slow_auth_path")

        redis_ctx = session.parent_context(trace_id, auth_span_id)
        with auth_tracer.start_as_current_span(
            "GET session",
            context=redis_ctx,
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "GET",
                "db.statement": "GET session:{token}",
                "peer.service": "redis-auth-cache",
            },
        ):
            total_duration += _sleep_ms(80, 250)

        total_duration += _sleep_ms(150, 400)

    session.record_http_server(
        service_name="demo-auth-service",
        duration_s=total_duration,
        method="GET",
        route="/auth/verify",
        status_code=200,
    )
    return format_trace_id(trace_id)


def search_mixed_db(session: OtlpSession) -> str:
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/search",
        kind=SpanKind.SERVER,
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id
        root.set_attribute("http.request.method", "GET")
        root.set_attribute("http.route", "/api/v1/search")
        root.set_attribute("http.response.status_code", 200)
        root.set_attribute("transaction.name", "WebTransaction/Action/search")
        _custom_attrs(root)
        root.set_attribute("feature.flag", "search_v2")

        db_specs = (
            ("mysql", "SELECT", "products_db", "products", "SELECT name FROM products WHERE q = ?"),
            ("mongodb", "aggregate", "catalog", "facets", "db.facets.aggregate([{$match: {q}}])"),
            ("redis", "GET", "cache", "search_cache", "GET search:cache:{hash}"),
        )
        for system, operation, db_name, collection, statement in db_specs:
            ctx = session.parent_context(trace_id, root_span_id)
            with gateway_tracer.start_as_current_span(
                f"{system} query",
                context=ctx,
                kind=SpanKind.CLIENT,
                attributes={
                    "db.system": system,
                    "db.operation": operation,
                    "db.name": db_name,
                    "db.collection": collection,
                    "db.statement": statement,
                    "peer.service": f"{system}-cluster",
                },
            ):
                total_duration += _sleep_ms(3, 20)

        total_duration += _sleep_ms(15, 45)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="GET",
        route="/api/v1/search",
        status_code=200,
    )
    return format_trace_id(trace_id)


def kafka_order_fulfilled(session: OtlpSession) -> str:
    worker_tracer = session.tracer("demo-notification-worker")
    total_duration = 0.0

    with worker_tracer.start_as_current_span(
        "process orders.completed",
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "kafka",
            "messaging.destination.name": "orders.completed",
            "messaging.operation": "process",
            "transaction.name": "OtherTransaction/Kafka/orders.completed",
        },
    ) as consumer:
        trace_id = consumer.get_span_context().trace_id
        consumer_span_id = consumer.get_span_context().span_id
        _custom_attrs(consumer)

        producer_ctx = session.parent_context(trace_id, consumer_span_id)
        with worker_tracer.start_as_current_span(
            "publish email.send",
            context=producer_ctx,
            kind=SpanKind.PRODUCER,
            attributes={
                "messaging.system": "kafka",
                "messaging.destination.name": "email.send",
                "messaging.operation": "publish",
            },
        ):
            total_duration += _sleep_ms(5, 20)

        total_duration += _sleep_ms(25, 70)

    session.record_messaging_process(
        service_name="demo-notification-worker",
        duration_s=total_duration,
        system="kafka",
        destination="orders.completed",
    )
    return format_trace_id(trace_id)


def grpc_inventory_check(session: OtlpSession) -> str:
    gateway_tracer = session.tracer("demo-api-gateway")
    inventory_tracer = session.tracer("demo-inventory-service")
    total_duration = 0.0
    sku = random_sku()

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/products/{id}",
        kind=SpanKind.SERVER,
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id
        root.set_attribute("http.request.method", "GET")
        root.set_attribute("http.route", "/api/v1/products/{id}")
        root.set_attribute("http.response.status_code", 200)
        root.set_attribute("transaction.name", "WebTransaction/Action/product_detail")

        inv_ctx = session.parent_context(trace_id, root_span_id)
        grpc_duration = _sleep_ms(8, 35)
        with inventory_tracer.start_as_current_span(
            "inventory.InventoryService/CheckStock",
            context=inv_ctx,
            kind=SpanKind.CLIENT,
            attributes={
                "rpc.system": "grpc",
                "rpc.service": "inventory.InventoryService",
                "rpc.method": "CheckStock",
                "server.address": "inventory.internal",
                "server.port": 50051,
                "net.peer.name": "inventory.internal",
            },
        ):
            pass
        session.record_http_client(
            service_name="demo-inventory-service",
            duration_s=grpc_duration,
            method="POST",
            url=f"grpc://inventory.internal:50051/CheckStock/{sku}",
            status_code=200,
        )
        total_duration += grpc_duration + _sleep_ms(10, 30)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="GET",
        route="/api/v1/products/{id}",
        status_code=200,
    )
    return format_trace_id(trace_id)


def high_cardinality_attributes(session: OtlpSession) -> str:
    """Search path with dense custom attributes for NRQL filtering."""
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/search",
        kind=SpanKind.SERVER,
    ) as root:
        trace_id = root.get_span_context().trace_id
        root.set_attribute("http.request.method", "GET")
        root.set_attribute("http.route", "/api/v1/search")
        root.set_attribute("http.response.status_code", 200)
        root.set_attribute("transaction.name", "WebTransaction/Action/search")
        root.set_attribute("customer.id", random_customer_id())
        root.set_attribute("order.id", random_order_id())
        root.set_attribute("feature.flag", random.choice(["on", "off", "beta"]))
        root.set_attribute("region", random.choice(["us-east-1", "eu-west-1", "ap-south-1"]))
        root.set_attribute("tenant.id", "tenant_" + random_order_id())
        root.set_attribute("experiment.id", random.choice(["exp_a", "exp_b", "control"]))
        total_duration += _sleep_ms(20, 80)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="GET",
        route="/api/v1/search",
        status_code=200,
    )
    return format_trace_id(trace_id)


SCENARIOS: list[tuple[ScenarioFn, int]] = [
    (checkout_happy_path, 25),
    (checkout_payment_failure, 15),
    (auth_slow_trace, 10),
    (search_mixed_db, 20),
    (kafka_order_fulfilled, 10),
    (grpc_inventory_check, 10),
    (high_cardinality_attributes, 10),
]


def pick_scenario() -> ScenarioFn:
    fns, weights = zip(*SCENARIOS)
    return random.choices(fns, weights=weights, k=1)[0]


def emit_random(session: OtlpSession) -> str:
    scenario = pick_scenario()
    return scenario(session)
