"""CtrlB/prod schema-aligned OTel attributes.

OTel dotted names flatten to underscore columns in CtrlB
(e.g. http.response.status_code → http_response_status_code).

Helpers emit both legacy and modern semconv keys so queries that
COALESCE(db_system_name, db_system) / http_response_status_code /
http_status_code keep working either way.
"""

from __future__ import annotations

from typing import Any


def http_server(
    *,
    method: str,
    route: str,
    status_code: int,
    target: str | None = None,
) -> dict[str, Any]:
    target = target or route
    return {
        "http.request.method": method,
        "http.method": method,
        "http.route": route,
        "http.target": target,
        "http.response.status_code": status_code,
        "http.status_code": status_code,
    }


def http_client(
    *,
    method: str,
    url: str,
    status_code: int,
    peer: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "http.request.method": method,
        "http.method": method,
        "http.url": url,
        "url.full": url,
        "http.response.status_code": status_code,
        "http.status_code": status_code,
    }
    if peer:
        attrs["server.address"] = peer
        attrs["net.peer.name"] = peer
    if port is not None:
        attrs["server.port"] = port
        attrs["net.peer.port"] = port
    return attrs


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
    response_status: str | None = None,
) -> dict[str, Any]:
    """NR-style DB identity: system + operation + target (table/collection/ns)."""
    attrs: dict[str, Any] = {
        "db.system": system,
        "db.system.name": system,
        "db.operation": operation,
        "db.operation.name": operation,
        "db.statement": statement,
    }
    if db_name:
        attrs["db.name"] = db_name
    if sql_table:
        attrs["db.sql.table"] = sql_table
    if mongodb_collection:
        attrs["db.mongodb.collection"] = mongodb_collection
    if namespace:
        attrs["db.namespace"] = namespace
    if peer:
        attrs["peer.service"] = peer
        attrs["server.address"] = peer
    if response_status is not None:
        attrs["db.response.status_code"] = response_status
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
    return {
        "rpc.system": system,
        "rpc.service": service,
        "rpc.method": method,
        "rpc.grpc.status_code": grpc_status,
        "server.address": peer,
        "server.port": port,
        "net.peer.name": peer,
        "net.peer.port": port,
    }


def messaging(
    *,
    system: str,
    destination: str,
    operation: str,
) -> dict[str, Any]:
    return {
        "messaging.system": system,
        "messaging.destination": destination,
        "messaging.destination.name": destination,
        "messaging.operation": operation,
    }
