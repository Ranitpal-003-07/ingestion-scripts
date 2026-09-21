"""Synthetic trace scenarios aligned to CtrlB APM query schema.

Emits SERVER/CLIENT spans with attributes that flatten to prod columns
(db_system_name, http_response_status_code, rpc_grpc_status_code, …)
so transaction + NR-style DB grouping queries return non-empty results.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from opentelemetry.trace import SpanKind, Status, StatusCode

from nr_traces import attrs, ids
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
    feature_flag: str = field(default_factory=lambda: random.choice(ids.FEATURE_FLAGS))
    experiment_id: str = field(default_factory=lambda: random.choice(ids.EXPERIMENTS))
    request_id: str = field(default_factory=ids.random_request_id)
    user_agent: str = field(default_factory=ids.random_user_agent)
    client_ip: str = field(default_factory=lambda: ids.random_ip(private=False))
    currency: str = field(default_factory=ids.random_currency)
    payment_method: str = field(default_factory=ids.random_payment_method)
    amount_cents: int = field(default_factory=random_amount_cents)
    user_email: str = field(default="")

    def __post_init__(self) -> None:
        if not self.user_email:
            self.user_email = ids.random_email(self.customer_id)

    def span_attrs(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = attrs.business(
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
                **(extra or {}),
            },
        )
        return payload


def _sleep_ms(low_ms: float, high_ms: float) -> float:
    duration_s = random.uniform(low_ms, high_ms) / 1000.0
    time.sleep(duration_s)
    return duration_s


def _apply(span, biz: Biz, extra: dict[str, Any] | None = None) -> None:
    for key, value in biz.span_attrs(extra).items():
        span.set_attribute(key, value)


def _mark_error(span, message: str, exc: BaseException | None = None) -> None:
    span.set_status(Status(StatusCode.ERROR, message))
    if exc is not None:
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
        span.set_attribute("error.message", str(exc))
        span.set_attribute("exception.stacktrace", "".join(
            [
                f"{type(exc).__name__}: {exc}\n",
                '  File "app.py", line 214, in handler\n',
                "    raise\n",
            ]
        ))
    else:
        span.set_attribute("error.type", "Error")
        span.set_attribute("error.message", message)


def _merge(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in parts:
        out.update(part)
    return out


def checkout_happy_path(session: OtlpSession) -> str:
    biz = Biz()
    total_duration = 0.0
    qty = random.randint(1, 4)

    gateway_tracer = session.tracer("demo-api-gateway")
    orders_tracer = session.tracer("demo-orders-service")
    payment_tracer = session.tracer("demo-payment-service")

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="POST",
                route="/api/v1/checkout",
                status_code=200,
                target="/api/v1/checkout",
                query=f"tenant={biz.tenant_id}",
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
                request_bytes=random.randint(900, 4200),
                response_bytes=random.randint(600, 1800),
            ),
            attrs.code_location(namespace="gateway.http.checkout", function="create_checkout"),
            biz.span_attrs({"http.route.matched": "checkout.create"}),
        ),
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        gateway_span_id = gateway_span.get_span_context().span_id
        gateway_span.add_event(
            "checkout.started",
            {"order.id": biz.order_id, "cart.items": qty},
        )

        orders_ctx = session.parent_context(trace_id, gateway_span_id)
        with orders_tracer.start_as_current_span(
            "POST /internal/orders",
            context=orders_ctx,
            kind=SpanKind.SERVER,
            attributes=_merge(
                attrs.http_server(
                    method="POST",
                    route="/internal/orders",
                    status_code=201,
                    host="orders.demo.internal",
                    scheme="http",
                    server_port=8080,
                    flavor="1.1",
                    user_agent="demo-api-gateway/2.8.1",
                    client_ip=ids.random_ip(),
                    request_bytes=random.randint(700, 2200),
                    response_bytes=random.randint(400, 1100),
                ),
                attrs.code_location(namespace="orders.api", function="create_order"),
                biz.span_attrs(),
            ),
        ) as orders_span:
            orders_span_id = orders_span.get_span_context().span_id

            validate_ctx = session.parent_context(trace_id, orders_span_id)
            with orders_tracer.start_as_current_span(
                "validate_cart",
                context=validate_ctx,
                kind=SpanKind.INTERNAL,
                attributes=_merge(
                    attrs.code_location(
                        namespace="orders.domain.cart", function="validate_cart"
                    ),
                    biz.span_attrs({"cart.item_count": qty}),
                ),
            ):
                total_duration += _sleep_ms(2, 12)

            redis_ctx = session.parent_context(trace_id, orders_span_id)
            cache_hit = random.random() < 0.65
            with orders_tracer.start_as_current_span(
                "GET cart",
                context=redis_ctx,
                kind=SpanKind.CLIENT,
                attributes=_merge(
                    attrs.redis_client(
                        operation="GET",
                        statement=f"GET cart:{biz.customer_id}",
                        namespace="cart",
                        peer="redis-cart.demo.internal",
                        args_length=1,
                        cache_hit=cache_hit,
                    ),
                    attrs.code_location(
                        namespace="orders.cache.redis", function="get_cart"
                    ),
                    biz.span_attrs(),
                ),
            ) as redis_span:
                redis_span.add_event(
                    "cache.hit" if cache_hit else "cache.miss",
                    {"cache.key": f"cart:{biz.customer_id}"},
                )
                total_duration += _sleep_ms(1, 8)

            for name, db_attrs, ns, fn, lo, hi in (
                (
                    "SELECT customers",
                    attrs.db_client(
                        system="postgresql",
                        operation="SELECT",
                        db_name="orders_db",
                        sql_table="customers",
                        statement="SELECT id, email, loyalty_tier FROM customers WHERE id = $1",
                        peer="postgresql-orders.demo.internal",
                        user="orders_app",
                        rows_affected=1,
                    ),
                    "orders.repo.customers",
                    "get_customer",
                    3,
                    14,
                ),
                (
                    "SELECT orders",
                    attrs.db_client(
                        system="postgresql",
                        operation="SELECT",
                        db_name="orders_db",
                        sql_table="orders",
                        statement="SELECT * FROM orders WHERE customer_id = $1 AND status = $2",
                        peer="postgresql-orders.demo.internal",
                        user="orders_app",
                        rows_affected=random.randint(0, 3),
                    ),
                    "orders.repo.orders",
                    "list_open_orders",
                    4,
                    18,
                ),
                (
                    "INSERT orders",
                    attrs.db_client(
                        system="postgresql",
                        operation="INSERT",
                        db_name="orders_db",
                        sql_table="orders",
                        statement=(
                            "INSERT INTO orders (id, customer_id, sku, amount_cents, currency) "
                            "VALUES ($1, $2, $3, $4, $5) RETURNING id"
                        ),
                        peer="postgresql-orders.demo.internal",
                        user="orders_app",
                        rows_affected=1,
                    ),
                    "orders.repo.orders",
                    "insert_order",
                    5,
                    20,
                ),
                (
                    "INSERT order_items",
                    attrs.db_client(
                        system="postgresql",
                        operation="INSERT",
                        db_name="orders_db",
                        sql_table="order_items",
                        statement=(
                            "INSERT INTO order_items (order_id, sku, qty, unit_cents) "
                            "VALUES ($1, $2, $3, $4)"
                        ),
                        peer="postgresql-orders.demo.internal",
                        user="orders_app",
                        rows_affected=qty,
                    ),
                    "orders.repo.items",
                    "insert_items",
                    3,
                    12,
                ),
            ):
                db_ctx = session.parent_context(trace_id, orders_span_id)
                with orders_tracer.start_as_current_span(
                    name,
                    context=db_ctx,
                    kind=SpanKind.CLIENT,
                    attributes=_merge(
                        db_attrs,
                        attrs.code_location(namespace=ns, function=fn),
                        biz.span_attrs(),
                    ),
                ):
                    total_duration += _sleep_ms(lo, hi)

            inv_ctx = session.parent_context(trace_id, orders_span_id)
            inv_duration = _sleep_ms(8, 28)
            inv_url = (
                f"http://inventory.demo.internal:8080/stock/{biz.sku}"
                f"?warehouse={biz.region}&qty={qty}"
            )
            with orders_tracer.start_as_current_span(
                "GET inventory",
                context=inv_ctx,
                kind=SpanKind.CLIENT,
                attributes=_merge(
                    attrs.http_client(
                        method="GET",
                        url=inv_url,
                        status_code=200,
                        peer="inventory.demo.internal",
                        port=8080,
                        peer_service="demo-inventory-service",
                        user_agent="demo-orders-service/1.19.4",
                        response_bytes=random.randint(180, 640),
                    ),
                    attrs.code_location(
                        namespace="orders.clients.inventory", function="check_stock"
                    ),
                    biz.span_attrs({"inventory.warehouse": biz.region, "inventory.qty": qty}),
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
            pay_duration = _sleep_ms(18, 55)
            stripe_url = "https://api.stripe.com/v1/payment_intents"
            with payment_tracer.start_as_current_span(
                "POST stripe.payment_intents",
                context=pay_ctx,
                kind=SpanKind.CLIENT,
                attributes=_merge(
                    attrs.http_client(
                        method="POST",
                        url=stripe_url,
                        status_code=200,
                        peer="api.stripe.com",
                        port=443,
                        peer_service="stripe",
                        user_agent="Stripe/v1 PythonBindings/7.8.0",
                        request_bytes=random.randint(400, 1200),
                        response_bytes=random.randint(800, 2400),
                    ),
                    attrs.code_location(
                        namespace="payments.stripe", function="create_payment_intent"
                    ),
                    biz.span_attrs(
                        {
                            "stripe.charge_id": "ch_" + biz.order_id[4:],
                            "stripe.payment_intent": "pi_" + biz.order_id[4:],
                            "peer.service": "stripe",
                        }
                    ),
                ),
            ):
                pass
            session.record_http_client(
                service_name="demo-payment-service",
                duration_s=pay_duration,
                method="POST",
                url=stripe_url,
                status_code=200,
            )
            total_duration += pay_duration

            kafka_ctx = session.parent_context(trace_id, orders_span_id)
            with orders_tracer.start_as_current_span(
                "publish orders.completed",
                context=kafka_ctx,
                kind=SpanKind.PRODUCER,
                attributes=_merge(
                    attrs.messaging(
                        system="kafka",
                        destination="orders.completed",
                        operation="publish",
                        destination_kind="topic",
                    ),
                    biz.span_attrs({"messaging.kafka.partition": random.randint(0, 11)}),
                ),
            ):
                total_duration += _sleep_ms(2, 10)

            total_duration += _sleep_ms(8, 22)

        total_duration += _sleep_ms(12, 35)
        gateway_span.add_event("checkout.succeeded", {"order.id": biz.order_id})

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
    biz = Biz()
    gateway_tracer = session.tracer("demo-api-gateway")
    orders_tracer = session.tracer("demo-orders-service")
    payment_tracer = session.tracer("demo-payment-service")
    total_duration = 0.0
    status_code = random.choice([500, 502, 503])

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="POST",
                route="/api/v1/checkout",
                status_code=status_code,
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
            ),
            attrs.code_location(namespace="gateway.http.checkout", function="create_checkout"),
            biz.span_attrs(),
        ),
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        gateway_span_id = gateway_span.get_span_context().span_id

        orders_ctx = session.parent_context(trace_id, gateway_span_id)
        with orders_tracer.start_as_current_span(
            "POST /internal/orders",
            context=orders_ctx,
            kind=SpanKind.SERVER,
            attributes=_merge(
                attrs.http_server(
                    method="POST",
                    route="/internal/orders",
                    status_code=status_code,
                    host="orders.demo.internal",
                    scheme="http",
                    server_port=8080,
                    user_agent="demo-api-gateway/2.8.1",
                    client_ip=ids.random_ip(),
                ),
                biz.span_attrs(),
            ),
        ) as orders_span:
            orders_span_id = orders_span.get_span_context().span_id

            db_ctx = session.parent_context(trace_id, orders_span_id)
            with orders_tracer.start_as_current_span(
                "SELECT payments",
                context=db_ctx,
                kind=SpanKind.CLIENT,
                attributes=_merge(
                    attrs.db_client(
                        system="postgresql",
                        operation="SELECT",
                        db_name="orders_db",
                        sql_table="payments",
                        statement="SELECT id, status FROM payments WHERE order_id = $1",
                        peer="postgresql-orders.demo.internal",
                        rows_affected=0,
                    ),
                    biz.span_attrs(),
                ),
            ):
                total_duration += _sleep_ms(4, 16)

            pay_ctx = session.parent_context(trace_id, orders_span_id)
            pay_duration = _sleep_ms(24, 80)
            stripe_url = "https://api.stripe.com/v1/charges"
            with payment_tracer.start_as_current_span(
                "POST stripe.charges",
                context=pay_ctx,
                kind=SpanKind.CLIENT,
                attributes=_merge(
                    attrs.http_client(
                        method="POST",
                        url=stripe_url,
                        status_code=502,
                        peer="api.stripe.com",
                        port=443,
                        peer_service="stripe",
                        user_agent="Stripe/v1 PythonBindings/7.8.0",
                        resend_count=2,
                    ),
                    biz.span_attrs({"stripe.error.code": "api_connection_error"}),
                ),
            ) as pay_span:
                pay_span.add_event("http.retry", {"http.request.resend_count": 1})
                pay_span.add_event("http.retry", {"http.request.resend_count": 2})
                _mark_error(
                    pay_span,
                    "Payment gateway unavailable",
                    RuntimeError("Payment gateway returned 502 Bad Gateway"),
                )
            session.record_http_client(
                service_name="demo-payment-service",
                duration_s=pay_duration,
                method="POST",
                url=stripe_url,
                status_code=502,
            )
            total_duration += pay_duration
            _mark_error(orders_span, "checkout failed")
            total_duration += _sleep_ms(8, 20)

        _mark_error(gateway_span, "checkout failed")
        total_duration += _sleep_ms(20, 50)

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
    biz = Biz()
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0
    status_code = random.choice([400, 404, 422])

    with gateway_tracer.start_as_current_span(
        "POST /api/v1/checkout",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="POST",
                route="/api/v1/checkout",
                status_code=status_code,
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
                response_bytes=random.randint(180, 500),
            ),
            biz.span_attrs({"error.expected": True, "http.status_reason": "client_error"}),
        ),
    ) as gateway_span:
        trace_id = gateway_span.get_span_context().trace_id
        _apply(gateway_span, biz)
        total_duration += _sleep_ms(4, 18)

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
    biz = Biz(feature_flag="slow_auth_path")
    auth_tracer = session.tracer("demo-auth-service")
    total_duration = 0.0

    with auth_tracer.start_as_current_span(
        "GET /auth/verify",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="GET",
                route="/auth/verify",
                status_code=200,
                host="auth.demo.shop",
                target=f"/auth/verify?session={biz.session_id}",
                query=f"session={biz.session_id}",
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
            ),
            attrs.code_location(namespace="auth.verify", function="verify_session"),
            biz.span_attrs(),
        ),
    ) as auth_span:
        trace_id = auth_span.get_span_context().trace_id
        auth_span_id = auth_span.get_span_context().span_id

        redis_ctx = session.parent_context(trace_id, auth_span_id)
        with auth_tracer.start_as_current_span(
            "GET session",
            context=redis_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.redis_client(
                    operation="GET",
                    statement=f"GET session:{biz.session_id}",
                    namespace="session",
                    peer="redis-auth-cache.demo.internal",
                    db_index=2,
                    args_length=1,
                    cache_hit=False,
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(80, 220)

        pg_ctx = session.parent_context(trace_id, auth_span_id)
        with auth_tracer.start_as_current_span(
            "SELECT users",
            context=pg_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.db_client(
                    system="postgresql",
                    operation="SELECT",
                    db_name="auth_db",
                    sql_table="users",
                    statement=(
                        "SELECT id, email, mfa_enabled, last_login_at FROM users WHERE id = $1"
                    ),
                    peer="postgresql-auth.demo.internal",
                    user="auth_app",
                    rows_affected=1,
                ),
                attrs.code_location(namespace="auth.repo.users", function="get_user"),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(12, 40)

        idp_ctx = session.parent_context(trace_id, auth_span_id)
        idp_url = "https://idp.okta.com/oauth2/v1/introspect"
        idp_duration = _sleep_ms(40, 120)
        with auth_tracer.start_as_current_span(
            "POST okta.introspect",
            context=idp_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.http_client(
                    method="POST",
                    url=idp_url,
                    status_code=200,
                    peer="idp.okta.com",
                    port=443,
                    peer_service="okta",
                    user_agent="demo-auth-service/4.1.0",
                ),
                biz.span_attrs({"idp.issuer": "https://idp.okta.com"}),
            ),
        ):
            pass
        session.record_http_client(
            service_name="demo-auth-service",
            duration_s=idp_duration,
            method="POST",
            url=idp_url,
            status_code=200,
        )
        total_duration += idp_duration + _sleep_ms(80, 180)

    session.record_http_server(
        service_name="demo-auth-service",
        duration_s=total_duration,
        method="GET",
        route="/auth/verify",
        status_code=200,
    )
    return format_trace_id(trace_id)


def search_mixed_db(session: OtlpSession) -> str:
    """Multiple NR-normalized DB keys plus elasticsearch + cache."""
    biz = Biz(feature_flag="search_v2")
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0
    query = random.choice(("running shoes", "wireless headphones", "office chair", biz.sku))

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/search",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="GET",
                route="/api/v1/search",
                status_code=200,
                target=f"/api/v1/search?q={query.replace(' ', '+')}&page=1",
                query=f"q={query}&page=1",
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
                response_bytes=random.randint(4000, 28000),
            ),
            attrs.code_location(namespace="gateway.http.search", function="search_products"),
            biz.span_attrs({"search.query": query, "search.page": 1}),
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id

        db_specs = (
            (
                "SELECT products",
                attrs.db_client(
                    system="mysql",
                    operation="SELECT",
                    db_name="products_db",
                    sql_table="products",
                    statement=(
                        "SELECT id, name, price_cents FROM products "
                        "WHERE MATCH(name) AGAINST (? IN NATURAL LANGUAGE MODE) LIMIT 50"
                    ),
                    peer="mysql-catalog.demo.internal",
                    user="catalog_ro",
                    rows_affected=random.randint(8, 50),
                ),
            ),
            (
                "elasticsearch search",
                attrs.elasticsearch_client(
                    operation="search",
                    index="products",
                    statement=(
                        '{"query":{"multi_match":{"query":"%s","fields":["name^3","brand"]}}}'
                        % query
                    ),
                    peer="es-search.demo.internal",
                ),
            ),
            (
                "mongodb aggregate",
                attrs.db_client(
                    system="mongodb",
                    operation="aggregate",
                    db_name="catalog",
                    mongodb_collection="facets",
                    statement='db.facets.aggregate([{"$match":{"q": "?"}},{"$group":{"_id":"$brand"}}])',
                    peer="mongodb-catalog.demo.internal",
                    user="catalog_app",
                    rows_affected=random.randint(4, 18),
                ),
            ),
            (
                "GET search_cache",
                attrs.redis_client(
                    operation="GET",
                    statement="GET search:cache:{hash}",
                    namespace="search_cache",
                    peer="redis-search.demo.internal",
                    cache_hit=random.random() < 0.4,
                ),
            ),
        )
        for name, db_attrs in db_specs:
            ctx = session.parent_context(trace_id, root_span_id)
            with gateway_tracer.start_as_current_span(
                name,
                context=ctx,
                kind=SpanKind.CLIENT,
                attributes=_merge(db_attrs, biz.span_attrs({"search.query": query})),
            ):
                total_duration += _sleep_ms(3, 22)

        rec_ctx = session.parent_context(trace_id, root_span_id)
        rec_url = "https://recommend.demo-external.com/v2/rank"
        rec_duration = _sleep_ms(12, 40)
        with gateway_tracer.start_as_current_span(
            "POST recommend.rank",
            context=rec_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.http_client(
                    method="POST",
                    url=rec_url,
                    status_code=200,
                    peer="recommend.demo-external.com",
                    port=443,
                    peer_service="recommendations",
                ),
                biz.span_attrs({"search.query": query}),
            ),
        ):
            pass
        session.record_http_client(
            service_name="demo-api-gateway",
            duration_s=rec_duration,
            method="POST",
            url=rec_url,
            status_code=200,
        )
        total_duration += rec_duration + _sleep_ms(8, 24)

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
    biz = Biz()
    orders_tracer = session.tracer("demo-orders-service")
    total_duration = 0.0

    with orders_tracer.start_as_current_span(
        "POST /internal/orders",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="POST",
                route="/internal/orders",
                status_code=500,
                host="orders.demo.internal",
                scheme="http",
                server_port=8080,
            ),
            biz.span_attrs(),
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id

        db_ctx = session.parent_context(trace_id, root_span_id)
        with orders_tracer.start_as_current_span(
            "INSERT orders",
            context=db_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.db_client(
                    system="postgresql",
                    operation="INSERT",
                    db_name="orders_db",
                    sql_table="orders",
                    statement="INSERT INTO orders (id, sku, customer_id) VALUES ($1, $2, $3)",
                    peer="postgresql-orders.demo.internal",
                    user="orders_app",
                    response_status="23505",
                    rows_affected=0,
                ),
                attrs.code_location(namespace="orders.repo.orders", function="insert_order"),
                biz.span_attrs({"db.sql.state": "23505"}),
            ),
        ) as db_span:
            _mark_error(
                db_span,
                "unique_violation",
                RuntimeError("duplicate key value violates unique constraint orders_pkey"),
            )
            total_duration += _sleep_ms(8, 28)

        _mark_error(root, "order insert failed")
        total_duration += _sleep_ms(4, 14)

    session.record_http_server(
        service_name="demo-orders-service",
        duration_s=total_duration,
        method="POST",
        route="/internal/orders",
        status_code=500,
    )
    return format_trace_id(trace_id)


def kafka_order_fulfilled(session: OtlpSession) -> str:
    biz = Biz()
    worker_tracer = session.tracer("demo-notification-worker")
    total_duration = 0.0
    receipt_key = f"receipts/{biz.region}/{biz.order_id}.pdf"

    with worker_tracer.start_as_current_span(
        "process orders.completed",
        kind=SpanKind.CONSUMER,
        attributes=_merge(
            attrs.messaging(
                system="kafka",
                destination="orders.completed",
                operation="process",
                destination_kind="topic",
            ),
            attrs.code_location(namespace="notify.worker", function="handle_order_completed"),
            biz.span_attrs({"messaging.kafka.partition": random.randint(0, 11)}),
        ),
    ) as consumer:
        trace_id = consumer.get_span_context().trace_id
        consumer_span_id = consumer.get_span_context().span_id

        pg_ctx = session.parent_context(trace_id, consumer_span_id)
        with worker_tracer.start_as_current_span(
            "SELECT orders",
            context=pg_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.db_client(
                    system="postgresql",
                    operation="SELECT",
                    db_name="orders_db",
                    sql_table="orders",
                    statement="SELECT id, email, amount_cents FROM orders WHERE id = $1",
                    peer="postgresql-orders.demo.internal",
                    rows_affected=1,
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(4, 16)

        s3_ctx = session.parent_context(trace_id, consumer_span_id)
        s3_duration = _sleep_ms(10, 35)
        with worker_tracer.start_as_current_span(
            "PUT s3.PutObject",
            context=s3_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.s3_client(
                    operation="PutObject",
                    bucket="demo-order-receipts",
                    key=receipt_key,
                    region=biz.region,
                ),
                biz.span_attrs(),
            ),
        ):
            pass
        session.record_http_client(
            service_name="demo-notification-worker",
            duration_s=s3_duration,
            method="PUT",
            url=f"https://demo-order-receipts.s3.{biz.region}.amazonaws.com/{receipt_key}",
            status_code=200,
        )
        total_duration += s3_duration

        twilio_ctx = session.parent_context(trace_id, consumer_span_id)
        twilio_url = "https://api.twilio.com/2010-04-01/Accounts/ACdemo/Messages.json"
        twilio_duration = _sleep_ms(15, 45)
        with worker_tracer.start_as_current_span(
            "POST twilio.messages",
            context=twilio_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.http_client(
                    method="POST",
                    url=twilio_url,
                    status_code=201,
                    peer="api.twilio.com",
                    port=443,
                    peer_service="twilio",
                    user_agent="twilio-python/8.10.0",
                ),
                biz.span_attrs({"twilio.sid": "SM" + biz.order_id[4:]}),
            ),
        ):
            pass
        session.record_http_client(
            service_name="demo-notification-worker",
            duration_s=twilio_duration,
            method="POST",
            url=twilio_url,
            status_code=201,
        )
        total_duration += twilio_duration

        producer_ctx = session.parent_context(trace_id, consumer_span_id)
        with worker_tracer.start_as_current_span(
            "publish email.send",
            context=producer_ctx,
            kind=SpanKind.PRODUCER,
            attributes=_merge(
                attrs.messaging(
                    system="kafka",
                    destination="email.send",
                    operation="publish",
                    destination_kind="topic",
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(3, 12)

        sqs_ctx = session.parent_context(trace_id, consumer_span_id)
        with worker_tracer.start_as_current_span(
            "send fulfillment.jobs",
            context=sqs_ctx,
            kind=SpanKind.PRODUCER,
            attributes=_merge(
                attrs.messaging(
                    system="sqs",
                    destination="fulfillment-jobs",
                    operation="publish",
                    destination_kind="queue",
                    region=biz.region,
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(4, 14)

        total_duration += _sleep_ms(10, 28)

    session.record_messaging_process(
        service_name="demo-notification-worker",
        duration_s=total_duration,
        system="kafka",
        destination="orders.completed",
    )
    return format_trace_id(trace_id)


def grpc_inventory_check(session: OtlpSession) -> str:
    biz = Biz()
    gateway_tracer = session.tracer("demo-api-gateway")
    inventory_tracer = session.tracer("demo-inventory-service")
    total_duration = 0.0

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/products/{id}",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="GET",
                route="/api/v1/products/{id}",
                status_code=200,
                target=f"/api/v1/products/{biz.sku}",
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
            ),
            biz.span_attrs(),
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id

        redis_ctx = session.parent_context(trace_id, root_span_id)
        with gateway_tracer.start_as_current_span(
            "GET inventory_cache",
            context=redis_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.redis_client(
                    operation="GET",
                    statement=f"GET inv:{biz.sku}",
                    namespace="inventory",
                    peer="redis-inventory.demo.internal",
                    cache_hit=False,
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(2, 9)

        inv_ctx = session.parent_context(trace_id, root_span_id)
        grpc_duration = _sleep_ms(8, 32)
        with inventory_tracer.start_as_current_span(
            "inventory.InventoryService/CheckStock",
            context=inv_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.rpc_client(
                    system="grpc",
                    service="inventory.InventoryService",
                    method="CheckStock",
                    peer="inventory.demo.internal",
                    port=50051,
                    grpc_status=0,
                ),
                attrs.code_location(
                    namespace="inventory.grpc", function="CheckStock"
                ),
                biz.span_attrs({"rpc.grpc.status_message": "OK"}),
            ),
        ):
            pass
        session.record_http_client(
            service_name="demo-inventory-service",
            duration_s=grpc_duration,
            method="POST",
            url=f"grpc://inventory.demo.internal:50051/CheckStock/{biz.sku}",
            status_code=200,
        )
        total_duration += grpc_duration

        pg_ctx = session.parent_context(trace_id, root_span_id)
        with inventory_tracer.start_as_current_span(
            "SELECT inventory",
            context=pg_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.db_client(
                    system="postgresql",
                    operation="SELECT",
                    db_name="inventory_db",
                    sql_table="inventory",
                    statement="SELECT sku, on_hand, reserved FROM inventory WHERE sku = $1",
                    peer="postgresql-inventory.demo.internal",
                    user="inventory_app",
                    rows_affected=1,
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(4, 16)

        total_duration += _sleep_ms(6, 18)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="GET",
        route="/api/v1/products/{id}",
        status_code=200,
    )
    return format_trace_id(trace_id)


def aws_session_lookup(session: OtlpSession) -> str:
    """DynamoDB + SQS external AWS services under an auth transaction."""
    biz = Biz()
    auth_tracer = session.tracer("demo-auth-service")
    total_duration = 0.0

    with auth_tracer.start_as_current_span(
        "POST /auth/session/refresh",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="POST",
                route="/auth/session/refresh",
                status_code=200,
                host="auth.demo.shop",
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
            ),
            biz.span_attrs(),
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        root_span_id = root.get_span_context().span_id

        ddb_ctx = session.parent_context(trace_id, root_span_id)
        with auth_tracer.start_as_current_span(
            "Query sessions",
            context=ddb_ctx,
            kind=SpanKind.CLIENT,
            attributes=_merge(
                attrs.dynamodb_client(
                    operation="Query",
                    table="demo-sessions",
                    region=biz.region,
                    count=1,
                    scanned_count=1,
                    statement="Query demo-sessions WHERE pk = :session_id",
                ),
                biz.span_attrs(),
            ),
        ):
            total_duration += _sleep_ms(8, 28)

        total_duration += _sleep_ms(6, 16)

    session.record_http_server(
        service_name="demo-auth-service",
        duration_s=total_duration,
        method="POST",
        route="/auth/session/refresh",
        status_code=200,
    )
    return format_trace_id(trace_id)


def high_cardinality_attributes(session: OtlpSession) -> str:
    biz = Biz()
    gateway_tracer = session.tracer("demo-api-gateway")
    total_duration = 0.0

    with gateway_tracer.start_as_current_span(
        "GET /api/v1/search",
        kind=SpanKind.SERVER,
        attributes=_merge(
            attrs.http_server(
                method="GET",
                route="/api/v1/search",
                status_code=200,
                user_agent=biz.user_agent,
                client_ip=biz.client_ip,
            ),
            biz.span_attrs(),
        ),
    ) as root:
        trace_id = root.get_span_context().trace_id
        total_duration += _sleep_ms(12, 40)

    session.record_http_server(
        service_name="demo-api-gateway",
        duration_s=total_duration,
        method="GET",
        route="/api/v1/search",
        status_code=200,
    )
    return format_trace_id(trace_id)


SCENARIOS: list[tuple[ScenarioFn, int]] = [
    (checkout_happy_path, 26),
    (checkout_payment_failure, 10),
    (checkout_client_error, 6),
    (auth_slow_trace, 10),
    (search_mixed_db, 16),
    (db_error_query, 6),
    (kafka_order_fulfilled, 10),
    (grpc_inventory_check, 8),
    (aws_session_lookup, 5),
    (high_cardinality_attributes, 3),
]


def pick_scenario() -> ScenarioFn:
    fns, weights = zip(*SCENARIOS)
    return random.choices(fns, weights=weights, k=1)[0]


def emit_random(session: OtlpSession) -> str:
    scenario = pick_scenario()
    return scenario(session)
