"""Synthetic trace scenarios aligned to CtrlB APM query schema.

Emits SERVER/CLIENT spans with attributes that flatten to prod columns
(db_system_name, http_response_status_code, rpc_grpc_status_code, …)
so transaction + NR-style DB grouping queries return non-empty results.
"""

from __future__ import annotations

import random
import time
from typing import Callable

from opentelemetry.trace import SpanKind, Status, StatusCode

from nr_traces import attrs
from nr_traces.ids import (
    format_trace_id,
    random_customer_id,
    random_order_id,
    random_sku,
)
from nr_traces.otlp import OtlpSession

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


def _mark_error(span, message: str, exc: BaseException | None = None) -> None:
    span.set_status(Status(StatusCode.ERROR, message))
    if exc is not None:
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        span.set_attribute("error.message", str(exc))
    else:
        span.set_attribute("error.type", "Error")
        span.set_attribute("error.message", message)


def checkout_happy_path(session: OtlpSession) -> str:
    sku = random_sku()
    total_duration = 0.0

    gateway_tracer = session.tracer("demo-api-gateway")
    orders_tracer = session.tracer("demo-orders-service")
    payment_tracer = session.tracer("demo-payment-service")

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="POST",
            route="/api/v1/checkout",
            status_code=200,
        ),
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        gateway_span_id = gateway_span.get_span_context().span_id
        _custom_attrs(gateway_span)
        gateway_span.set_attribute(
            "region", random.choice(["us-east", "eu-west", "ap-south"])
        )

        orders_ctx = session.parent_context(trace_id, gateway_span_id)
        with orders_tracer.start_as_current_span(
            "POST /internal/orders",
            context=orders_ctx,
            kind=SpanKind.SERVER,
            attributes=attrs.http_server(
                method="POST",
                route="/internal/orders",
                status_code=200,
            ),
        ) as orders_span:
            orders_span_id = orders_span.get_span_context().span_id

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
                attributes=attrs.db_client(
                    system="postgresql",
                    operation="SELECT",
                    db_name="orders_db",
                    sql_table="orders",
                    statement="SELECT * FROM orders WHERE id = $1",
                    peer="postgresql-orders",
                ),
            ):
                total_duration += _sleep_ms(5, 25)

            inv_ctx = session.parent_context(trace_id, orders_span_id)
            inv_duration = _sleep_ms(10, 40)
            inv_url = f"http://inventory:8080/stock/{sku}"
            with orders_tracer.start_as_current_span(
                "GET inventory",
                context=inv_ctx,
                kind=SpanKind.CLIENT,
                attributes=attrs.http_client(
                    method="GET",
                    url=inv_url,
                    status_code=200,
                    peer="inventory",
                    port=8080,
                ),
            ):
                pass
            session.record_http_client(
                service_name="demo-orders-service",
                duration_s=inv_duration,
                method="GET",
                url=inv_url,
                status_code=200,
            )
            total_duration += inv_duration

            pay_ctx = session.parent_context(trace_id, orders_span_id)
            pay_duration = _sleep_ms(15, 50)
            with payment_tracer.start_as_current_span(
                "POST charge",
                context=pay_ctx,
                kind=SpanKind.CLIENT,
                attributes=attrs.http_client(
                    method="POST",
                    url="https://payments.example.com/charge",
                    status_code=200,
                    peer="payments.example.com",
                ),
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
    """5xx + span ERROR — counted as NR-default errors."""
    gateway_tracer = session.tracer("demo-api-gateway")
    orders_tracer = session.tracer("demo-orders-service")
    payment_tracer = session.tracer("demo-payment-service")
    total_duration = 0.0
    status_code = random.choice([500, 502, 503])

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="POST",
            route="/api/v1/checkout",
            status_code=status_code,
        ),
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        gateway_span_id = gateway_span.get_span_context().span_id
        _custom_attrs(gateway_span)

        orders_ctx = session.parent_context(trace_id, gateway_span_id)
        with orders_tracer.start_as_current_span(
            "POST /internal/orders",
            context=orders_ctx,
            kind=SpanKind.SERVER,
            attributes=attrs.http_server(
                method="POST",
                route="/internal/orders",
                status_code=status_code,
            ),
        ) as orders_span:
            orders_span_id = orders_span.get_span_context().span_id

            pay_ctx = session.parent_context(trace_id, orders_span_id)
            pay_duration = _sleep_ms(20, 60)
            with payment_tracer.start_as_current_span(
                "POST charge",
                context=pay_ctx,
                kind=SpanKind.CLIENT,
                attributes=attrs.http_client(
                    method="POST",
                    url="https://payments.example.com/charge",
                    status_code=502,
                    peer="payments.example.com",
                ),
            ) as pay_span:
                _mark_error(
                    pay_span,
                    "Payment gateway unavailable",
                    RuntimeError("Payment gateway returned 502 Bad Gateway"),
                )
            session.record_http_client(
                service_name="demo-payment-service",
                duration_s=pay_duration,
                method="POST",
                url="https://payments.example.com/charge",
                status_code=502,
            )
            total_duration += pay_duration
            _mark_error(orders_span, "checkout failed")
            total_duration += _sleep_ms(10, 30)

        _mark_error(gateway_span, "checkout failed")
        total_duration += _sleep_ms(40, 100)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="POST",
        route="/api/v1/checkout",
        status_code=status_code,
    )
    return format_trace_id(trace_id)


def checkout_client_error(session: OtlpSession) -> str:
    """4xx only — should NOT inflate NR-default error rate (5xx+exceptions)."""
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0
    status_code = random.choice([400, 404, 422])

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="POST",
            route="/api/v1/checkout",
            status_code=status_code,
        ),
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        _custom_attrs(gateway_span)
        total_duration += _sleep_ms(5, 25)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="POST",
        route="/api/v1/checkout",
        status_code=status_code,
    )
    return format_trace_id(trace_id)


def auth_slow_trace(session: OtlpSession) -> str:
    """Slow SERVER txn + redis CLIENT for apdex / slowest_avg cards."""
    auth_tracer = session.tracer("demo-auth-service")
    total_duration = 0.0

    with auth_tracer.start_as_current_span(
        "GET /auth/verify",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="GET",
            route="/auth/verify",
            status_code=200,
        ),
    ) as auth_span:
        trace_id = auth_span.get_span_context().trace_id
        auth_span_id = auth_span.get_span_context().span_id
        _custom_attrs(auth_span, **{"feature.flag": "slow_auth_path"})

        redis_ctx = session.parent_context(trace_id, auth_span_id)
        with auth_tracer.start_as_current_span(
            "GET session",
            context=redis_ctx,
            kind=SpanKind.CLIENT,
            attributes=attrs.db_client(
                system="redis",
                operation="GET",
                namespace="session",
                statement="GET session:{token}",
                peer="redis-auth-cache",
            ),
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
    """Multiple NR-normalized DB keys: MySQL·products·SELECT, Mongo·facets·aggregate, Redis."""
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/search",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="GET",
            route="/api/v1/search",
            status_code=200,
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id
        _custom_attrs(root, **{"feature.flag": "search_v2"})

        db_specs = (
            attrs.db_client(
                system="mysql",
                operation="SELECT",
                db_name="products_db",
                sql_table="products",
                statement="SELECT name FROM products WHERE q = ?",
                peer="mysql-cluster",
            ),
            attrs.db_client(
                system="mongodb",
                operation="aggregate",
                db_name="catalog",
                mongodb_collection="facets",
                statement="db.facets.aggregate([{$match: {q}}])",
                peer="mongodb-cluster",
            ),
            attrs.db_client(
                system="redis",
                operation="GET",
                namespace="search_cache",
                statement="GET search:cache:{hash}",
                peer="redis-cluster",
            ),
        )
        for db_attrs in db_specs:
            system = db_attrs["db.system"]
            ctx = session.parent_context(trace_id, root_span_id)
            with gateway_tracer.start_as_current_span(
                f"{system} query",
                context=ctx,
                kind=SpanKind.CLIENT,
                attributes=db_attrs,
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


def db_error_query(session: OtlpSession) -> str:
    """DB CLIENT span with error status + db_response_status_code 5xx."""
    orders_tracer = session.tracer("demo-orders-service")
    total_duration = 0.0

    with orders_tracer.start_as_current_span(
        "POST /internal/orders",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="POST",
            route="/internal/orders",
            status_code=500,
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id
        _custom_attrs(root)

        db_ctx = session.parent_context(trace_id, root_span_id)
        with orders_tracer.start_as_current_span(
            "INSERT orders",
            context=db_ctx,
            kind=SpanKind.CLIENT,
            attributes=attrs.db_client(
                system="postgresql",
                operation="INSERT",
                db_name="orders_db",
                sql_table="orders",
                statement="INSERT INTO orders (id, sku) VALUES ($1, $2)",
                peer="postgresql-orders",
                response_status="500",
            ),
        ) as db_span:
            _mark_error(
                db_span,
                "unique_violation",
                RuntimeError("duplicate key value violates unique constraint"),
            )
            total_duration += _sleep_ms(10, 40)

        _mark_error(root, "order insert failed")
        total_duration += _sleep_ms(5, 20)

    session.record_http_server(
        service_name="demo-orders-service",
        duration_s=total_duration,
        method="POST",
        route="/internal/orders",
        status_code=500,
    )
    return format_trace_id(trace_id)


def kafka_order_fulfilled(session: OtlpSession) -> str:
    worker_tracer = session.tracer("demo-notification-worker")
    total_duration = 0.0

    with worker_tracer.start_as_current_span(
        "process orders.completed",
        kind=SpanKind.CONSUMER,
        attributes=attrs.messaging(
            system="kafka",
            destination="orders.completed",
            operation="process",
        ),
    ) as consumer:
        trace_id = consumer.get_span_context().trace_id
        consumer_span_id = consumer.get_span_context().span_id
        _custom_attrs(consumer)

        producer_ctx = session.parent_context(trace_id, consumer_span_id)
        with worker_tracer.start_as_current_span(
            "publish email.send",
            context=producer_ctx,
            kind=SpanKind.PRODUCER,
            attributes=attrs.messaging(
                system="kafka",
                destination="email.send",
                operation="publish",
            ),
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
        attributes=attrs.http_server(
            method="GET",
            route="/api/v1/products/{id}",
            status_code=200,
            target=f"/api/v1/products/{sku}",
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id

        inv_ctx = session.parent_context(trace_id, root_span_id)
        grpc_duration = _sleep_ms(8, 35)
        with inventory_tracer.start_as_current_span(
            "inventory.InventoryService/CheckStock",
            context=inv_ctx,
            kind=SpanKind.CLIENT,
            attributes=attrs.rpc_client(
                system="grpc",
                service="inventory.InventoryService",
                method="CheckStock",
                peer="inventory.internal",
                port=50051,
                grpc_status=0,
            ),
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
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/search",
        kind=SpanKind.SERVER,
        attributes=attrs.http_server(
            method="GET",
            route="/api/v1/search",
            status_code=200,
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root.set_attribute("customer.id", random_customer_id())
        root.set_attribute("order.id", random_order_id())
        root.set_attribute("feature.flag", random.choice(["on", "off", "beta"]))
        root.set_attribute(
            "region", random.choice(["us-east-1", "eu-west-1", "ap-south-1"])
        )
        root.set_attribute("tenant.id", "tenant_" + random_order_id())
        root.set_attribute(
            "experiment.id", random.choice(["exp_a", "exp_b", "control"])
        )
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
    (checkout_happy_path, 22),
    (checkout_payment_failure, 12),
    (checkout_client_error, 8),
    (auth_slow_trace, 10),
    (search_mixed_db, 18),
    (db_error_query, 8),
    (kafka_order_fulfilled, 8),
    (grpc_inventory_check, 8),
    (high_cardinality_attributes, 6),
]


def pick_scenario() -> ScenarioFn:
    fns, weights = zip(*SCENARIOS)
    return random.choices(fns, weights=weights, k=1)[0]


def emit_random(session: OtlpSession) -> str:
    scenario = pick_scenario()
    return scenario(session)
