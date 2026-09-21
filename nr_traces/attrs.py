"""CtrlB/prod schema-aligned OTel attributes.

OTel dotted names flatten to underscore columns in CtrlB
(e.g. http.response.status_code → http_response_status_code).

Helpers emit both legacy and modern semconv keys so queries that
COALESCE(db_system_name, db_system) / http_response_status_code /
http_status_code keep working either way.
"""

from __future__ import annotations

import random
from typing import Any
from urllib.parse import urlparse

from nr_traces import ids


def _omit_none(attrs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in attrs.items() if v is not None}


def business(
    *,
    customer_id: str,
    order_id: str | None = None,
    sku: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    region: str | None = None,
    feature_flag: str | None = None,
    experiment_id: str | None = None,
    request_id: str | None = None,
    user_email: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "customer.id": customer_id,
        "order.id": order_id,
        "sku": sku,
        "session.id": session_id,
        "tenant.id": tenant_id,
        "region": region,
        "cloud.region": region,
        "feature.flag": feature_flag,
        "experiment.id": experiment_id,
        "request.id": request_id,
        "enduser.id": customer_id,
        "user.email": user_email,
    }
    if extra:
        payload.update(extra)
    return _omit_none(payload)


def code_location(*, namespace: str, function: str, thread_name: str | None = None) -> dict[str, Any]:
    return {
        "code.namespace": namespace,
        "code.function": function,
        "thread.id": random.randint(11, 64),
        "thread.name": thread_name
        or random.choice(
            (
                f"http-nio-8080-exec-{random.randint(1, 16)}",
                "asyncio-worker-0",
                "gunicorn.workers",
            )
        ),
    }


def http_server(
    *,
    method: str,
    route: str,
    status_code: int,
    target: str | None = None,
    host: str = "api.demo.shop",
    scheme: str = "https",
    flavor: str | None = None,
    user_agent: str | None = None,
    client_ip: str | None = None,
    query: str | None = None,
    request_bytes: int | None = None,
    response_bytes: int | None = None,
    server_name: str | None = None,
    server_port: int = 443,
) -> dict[str, Any]:
    target = target or route
    flavor = flavor or random.choice(ids.HTTP_FLAVORS)
    user_agent = user_agent or ids.random_user_agent()
    client_ip = client_ip or ids.random_ip(private=False)
    request_bytes = request_bytes if request_bytes is not None else random.randint(180, 2400)
    response_bytes = response_bytes if response_bytes is not None else random.randint(420, 18000)
    path = target.split("?", 1)[0]
    return _omit_none(
        {
            "http.request.method": method,
            "http.method": method,
            "http.route": route,
            "http.target": target,
            "http.response.status_code": status_code,
            "http.status_code": status_code,
            "http.host": host,
            "http.scheme": scheme,
            "http.flavor": flavor,
            "http.server_name": server_name or host,
            "http.user_agent": user_agent,
            "user_agent.original": user_agent,
            "http.client_ip": client_ip,
            "client.address": client_ip,
            "http.request.content_length": request_bytes,
            "http.response.content_length": response_bytes,
            "net.host.name": host,
            "net.host.port": server_port,
            "net.protocol.name": "http",
            "net.protocol.version": flavor,
            "net.transport": "ip_tcp",
            "network.protocol.version": flavor,
            "network.transport": "tcp",
            "network.type": "ipv4",
            "url.scheme": scheme,
            "url.path": path,
            "url.query": query,
            "url.full": f"{scheme}://{host}{target}",
            "server.address": host,
            "server.port": server_port,
            "http.request.header.user_agent": user_agent,
            "http.request.header.accept_encoding": "gzip, deflate, br",
            "http.request.header.traceparent": "00",
            "http.request.header._authority": host,
            "http.request.header._method": method,
            "http.request.header._path": target,
            "http.request.header._scheme": scheme,
        }
    )


def http_client(
    *,
    method: str,
    url: str,
    status_code: int,
    peer: str | None = None,
    port: int | None = None,
    peer_service: str | None = None,
    user_agent: str | None = None,
    request_bytes: int | None = None,
    response_bytes: int | None = None,
    resend_count: int = 0,
    flavor: str = "1.1",
) -> dict[str, Any]:
    parsed = urlparse(url)
    peer = peer or parsed.hostname or "unknown"
    if port is None:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    user_agent = user_agent or "demo-orders-service/2.4.0 otel/1.27"
    request_bytes = request_bytes if request_bytes is not None else random.randint(120, 1800)
    response_bytes = response_bytes if response_bytes is not None else random.randint(80, 9000)
    peer_ip = ids.random_ip()
    return _omit_none(
        {
            "http.request.method": method,
            "http.method": method,
            "http.url": url,
            "url.full": url,
            "url.scheme": parsed.scheme or "https",
            "url.path": parsed.path or "/",
            "url.query": parsed.query or None,
            "http.response.status_code": status_code,
            "http.status_code": status_code,
            "http.host": peer,
            "http.scheme": parsed.scheme or "https",
            "http.flavor": flavor,
            "http.user_agent": user_agent,
            "user_agent.original": user_agent,
            "http.request.content_length": request_bytes,
            "http.response.content_length": response_bytes,
            "http.request.resend_count": resend_count,
            "retry.attempts": resend_count,
            "server.address": peer,
            "server.port": port,
            "net.peer.name": peer,
            "net.peer.port": port,
            "net.peer.ip": peer_ip,
            "net.sock.peer.addr": peer_ip,
            "net.sock.peer.port": port,
            "net.sock.peer.name": peer,
            "net.transport": "ip_tcp",
            "net.protocol.name": "http",
            "net.protocol.version": flavor,
            "network.peer.address": peer_ip,
            "network.peer.port": port,
            "network.protocol.version": flavor,
            "network.transport": "tcp",
            "network.type": "ipv4",
            "peer.service": peer_service or peer,
        }
    )


def db_client(
    *,
    system: str,
    operation: str,
    statement: str,
    db_name: str | None = None,
    sql_table: str | None = None,
    mongodb_collection: str | None = None,
    namespace: str | None = None,
    peer: str | None = None,
    port: int | None = None,
    user: str | None = None,
    response_status: str | None = None,
    rows_affected: int | None = None,
    connection_string: str | None = None,
    peer_ip: str | None = None,
) -> dict[str, Any]:
    """NR-style DB identity: system + operation + target (table/collection/ns)."""
    default_ports = {
        "postgresql": 5432,
        "mysql": 3306,
        "mongodb": 27017,
        "redis": 6379,
        "elasticsearch": 9200,
        "dynamodb": 443,
    }
    port = port if port is not None else default_ports.get(system, 5432)
    user = user or {
        "postgresql": "orders_app",
        "mysql": "catalog_ro",
        "mongodb": "catalog_app",
        "redis": "cache_app",
        "elasticsearch": "search_app",
        "dynamodb": "iam:demo-orders",
    }.get(system, "app_user")
    peer = peer or f"{system}-primary"
    peer_ip = peer_ip or ids.random_ip()
    if connection_string is None and system in ("postgresql", "mysql"):
        db = db_name or "app"
        connection_string = f"{system}://{user}@{peer}:{port}/{db}"
    elif connection_string is None and system == "redis":
        connection_string = f"redis://{peer}:{port}/0"
    elif connection_string is None and system == "mongodb":
        connection_string = f"mongodb://{user}@{peer}:{port}/{db_name or 'catalog'}"
    elif connection_string is None and system == "elasticsearch":
        connection_string = f"https://{peer}:{port}"

    attrs: dict[str, Any] = {
        "db.system": system,
        "db.system.name": system,
        "db.operation": operation,
        "db.operation.name": operation,
        "db.statement": statement,
        "db.name": db_name,
        "db.sql.table": sql_table,
        "db.mongodb.collection": mongodb_collection,
        "db.namespace": namespace or db_name,
        "db.user": user,
        "db.connection_string": connection_string,
        "db.response.status_code": response_status,
        "db.rows_affected": None if rows_affected is None else str(rows_affected),
        "peer.service": peer,
        "server.address": peer,
        "server.port": port,
        "net.peer.name": peer,
        "net.peer.port": port,
        "net.peer.ip": peer_ip,
        "net.sock.peer.addr": peer_ip,
        "net.sock.peer.port": port,
        "net.sock.peer.name": peer,
        "net.transport": "ip_tcp",
        "network.peer.address": peer_ip,
        "network.peer.port": port,
        "network.transport": "tcp",
        "network.type": "ipv4",
    }
    return _omit_none(attrs)


def redis_client(
    *,
    operation: str,
    statement: str,
    namespace: str = "session",
    peer: str = "redis-cluster",
    db_index: int = 0,
    args_length: int = 2,
    pipeline_length: int = 1,
    cache_hit: bool | None = None,
) -> dict[str, Any]:
    attrs = db_client(
        system="redis",
        operation=operation,
        statement=statement,
        namespace=namespace,
        peer=peer,
        port=6379,
        user="cache_app",
        rows_affected=1 if cache_hit else 0,
    )
    attrs.update(
        {
            "db.redis.database_index": str(db_index),
            "db.redis.args_length": str(args_length),
            "db.redis.pipeline_length": str(pipeline_length),
        }
    )
    if cache_hit is not None:
        attrs["cache.hit"] = cache_hit
    return attrs


def elasticsearch_client(
    *,
    operation: str,
    statement: str,
    index: str,
    peer: str = "es-search-data.demo.internal",
    node_name: str | None = None,
) -> dict[str, Any]:
    attrs = db_client(
        system="elasticsearch",
        operation=operation,
        statement=statement,
        db_name=index,
        namespace=index,
        peer=peer,
        port=9200,
        user="search_app",
    )
    attrs["elasticsearch.node.name"] = node_name or random.choice(
        ("es-data-0", "es-data-1", "es-data-2")
    )
    return attrs


def dynamodb_client(
    *,
    operation: str,
    table: str,
    region: str,
    count: int = 1,
    scanned_count: int | None = None,
    statement: str | None = None,
) -> dict[str, Any]:
    peer = f"dynamodb.{region}.amazonaws.com"
    attrs = db_client(
        system="dynamodb",
        operation=operation,
        statement=statement or f"{operation} {table}",
        db_name=table,
        sql_table=table,
        namespace=table,
        peer=peer,
        port=443,
        user="iam:demo-orders",
        rows_affected=count,
        connection_string=f"https://{peer}",
    )
    attrs.update(
        {
            "aws.region": region,
            "aws.request_id": ids.random_aws_request_id(),
            "aws.dynamodb.table_names": table,
            "aws.dynamodb.count": str(count),
            "aws.dynamodb.scanned_count": str(
                scanned_count if scanned_count is not None else count
            ),
            "faas.invoked_name": "dynamodb",
            "faas.invoked_provider": "aws",
            "faas.invoked_region": region,
        }
    )
    return attrs


def s3_client(
    *,
    operation: str,
    bucket: str,
    key: str,
    region: str,
    status_code: int = 200,
) -> dict[str, Any]:
    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    attrs = http_client(
        method="PUT" if operation.lower() in ("putobject", "upload") else "GET",
        url=url,
        status_code=status_code,
        peer=f"{bucket}.s3.{region}.amazonaws.com",
        port=443,
        peer_service="aws.s3",
        user_agent="aws-sdk-python/1.34.0",
    )
    attrs.update(
        {
            "s3.bucket": bucket,
            "s3.key": key,
            "aws.region": region,
            "aws.request_id": ids.random_aws_request_id(),
            "rpc.system": "aws-api",
            "rpc.service": "S3",
            "rpc.method": operation,
        }
    )
    return attrs


def rpc_client(
    *,
    system: str,
    service: str,
    method: str,
    peer: str,
    port: int = 50051,
    grpc_status: int = 0,
) -> dict[str, Any]:
    peer_ip = ids.random_ip()
    return {
        "rpc.system": system,
        "rpc.service": service,
        "rpc.method": method,
        "rpc.grpc.status_code": grpc_status,
        "server.address": peer,
        "server.port": port,
        "net.peer.name": peer,
        "net.peer.port": port,
        "net.peer.ip": peer_ip,
        "net.sock.peer.addr": peer_ip,
        "net.sock.peer.port": port,
        "net.transport": "ip_tcp",
        "network.peer.address": peer_ip,
        "network.peer.port": port,
        "network.transport": "tcp",
        "network.protocol.version": "grpc",
        "network.type": "ipv4",
        "peer.service": service,
    }


def messaging(
    *,
    system: str,
    destination: str,
    operation: str,
    destination_kind: str = "topic",
    message_id: str | None = None,
    url: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    message_id = message_id or ids.random_message_id()
    if system == "kafka":
        url = url or f"kafka://kafka-orders.demo.internal:9092/{destination}"
    elif system == "sqs":
        url = url or (
            f"https://sqs.{region or 'us-east-1'}.amazonaws.com/123456789012/{destination}"
        )
    payload = {
        "messaging.system": system,
        "messaging.destination": destination,
        "messaging.destination.name": destination,
        "messaging.destination.kind": destination_kind,
        "messaging.operation": operation,
        "messaging.message.id": message_id,
        "messaging.url": url,
        "peer.service": system,
    }
    if system == "sqs":
        payload["aws.sqs.queue.url"] = url
        payload["aws.queue_url"] = url
        payload["aws.region"] = region or "us-east-1"
        payload["aws.request_id"] = ids.random_aws_request_id()
        payload["sqs.handler"] = "OrderFulfilledHandler"
    return _omit_none(payload)
