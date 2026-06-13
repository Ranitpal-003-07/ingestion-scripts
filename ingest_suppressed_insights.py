import random
import time

import requests

ENDPOINT = "http://staging.ctrlb.dev:8080/api/default/suppressed_insights_test/_json_evolving"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "MetricsGenerator/1.0",
}

LOGS_PER_SECOND = 30

SERVICES = ["checkout-api", "search-api", "auth-service", "order-processor", "api-gateway", "worker-queue"]
ENVIRONMENT = "staging"
HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]
URIS = [
    "/api/v1/checkout",
    "/api/v1/search",
    "/api/v1/login",
    "/api/v1/orders",
    "/api/v1/payments",
    "/health",
]
FAILURE_REASONS = ["invalid_password", "account_locked", "expired_token", "unknown_user"]
DOWNSTREAM_SERVICES = ["payment-gateway", "inventory-service", "notification-service", "fraud-check"]

_log_counter = 0


def random_ip():
    return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def make_base(service: str, insight_type: str, log_level: str, message: str) -> dict:
    now_us = int(time.time() * 1_000_000)
    return {
        "_timestamp": now_us,
        "timestamp": now_us,
        "ctrlb_timestamp": now_us,
        "service": service,
        "environment": ENVIRONMENT,
        "log_level": log_level,
        "insight_type": insight_type,
        "message": message,
        "trace_id": f"tr-{random.randint(1, 99999999):08x}",
        "host": f"{service.replace('_', '-')}-{random.randint(1000, 9999)}-{random.choice('abcdef0123456789')}{random.choice('abcdef0123456789')}{random.choice('abcdef0123456789')}{random.choice('abcdef0123456789')}",
    }


def generate_error_rate_spike():
    service = random.choice(SERVICES)
    method = random.choice(HTTP_METHODS)
    uri = random.choice(URIS)
    status = random.choice([500, 502, 503, 504])
    log = make_base(
        service,
        "error_rate_spike",
        "ERROR",
        f"HTTP {status} Internal Server Error on {method} {uri}",
    )
    log.update(
        {
            "status_code": status,
            "method": method,
            "uri": uri,
            "latency_ms": round(random.uniform(800.0, 2500.0), 1),
        }
    )
    return log


def generate_latency_anomaly():
    service = random.choice(SERVICES)
    method = random.choice(HTTP_METHODS)
    uri = random.choice(URIS)
    latency = round(random.uniform(1500.0, 5000.0), 1)
    threshold = round(random.uniform(300.0, 800.0), 1)
    log = make_base(
        service,
        "latency_anomaly",
        "WARN",
        f"Request exceeded p99 threshold: {latency}ms on {method} {uri}",
    )
    log.update(
        {
            "status_code": 200,
            "method": method,
            "uri": uri,
            "latency_ms": latency,
            "threshold_ms": threshold,
        }
    )
    return log


def generate_auth_failure_burst():
    service = "auth-service"
    reason = random.choice(FAILURE_REASONS)
    log = make_base(
        service,
        "auth_failure_burst",
        "WARN",
        f"Authentication failed: {reason.replace('_', ' ')} for user login attempt",
    )
    log.update(
        {
            "client_ip": random_ip(),
            "user_agent": random.choice(
                [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Mozilla/5.0 (Linux; Android 14)",
                ]
            ),
            "failure_reason": reason,
        }
    )
    return log


def generate_dependency_timeout():
    service = random.choice(["order-processor", "checkout-api", "search-api"])
    downstream = random.choice(DOWNSTREAM_SERVICES)
    timeout_ms = random.choice([3000, 5000, 8000, 10000])
    log = make_base(
        service,
        "dependency_timeout",
        "ERROR",
        f"Downstream call timed out: {downstream} after {timeout_ms}ms",
    )
    log.update(
        {
            "downstream_service": downstream,
            "timeout_ms": timeout_ms,
            "retry_count": random.randint(0, 3),
        }
    )
    return log


def generate_rate_limit_exceeded():
    service = "api-gateway"
    limit_rpm = random.choice([500, 1000, 2000])
    current_rpm = limit_rpm + random.randint(50, 500)
    client_ip = random_ip()
    log = make_base(
        service,
        "rate_limit_exceeded",
        "WARN",
        f"Rate limit exceeded: {current_rpm} req/min from client {client_ip}",
    )
    log.update(
        {
            "client_ip": client_ip,
            "limit_rpm": limit_rpm,
            "current_rpm": current_rpm,
        }
    )
    return log


def generate_resource_pressure():
    service = random.choice(["worker-queue", "order-processor", "search-api"])
    memory_pct = round(random.uniform(85.0, 98.0), 1)
    threshold = round(random.uniform(80.0, 90.0), 1)
    cpu_pct = round(random.uniform(60.0, 95.0), 1)
    log = make_base(
        service,
        "resource_pressure",
        "WARN",
        f"Memory usage above threshold: {memory_pct}% on {service} pod",
    )
    log.update(
        {
            "memory_pct": memory_pct,
            "cpu_pct": cpu_pct,
            "threshold_pct": threshold,
        }
    )
    return log


GENERATORS = [
    generate_error_rate_spike,
    generate_latency_anomaly,
    generate_auth_failure_burst,
    generate_dependency_timeout,
    generate_rate_limit_exceeded,
    generate_resource_pressure,
]


def generate_log():
    global _log_counter

    log = GENERATORS[_log_counter % len(GENERATORS)]()
    _log_counter += 1
    return log


def send_logs():
    session = requests.Session()
    session.headers.update(HEADERS)

    print(
        f"Starting suppressed insights log ingestion ({LOGS_PER_SECOND} logs/sec) "
        f"with {len(GENERATORS)} insight types..."
    )

    while True:
        start_time = time.time()

        batch = [generate_log() for _ in range(LOGS_PER_SECOND)]

        try:
            response = session.post(ENDPOINT, json=batch, timeout=10)

            if response.status_code == 200:
                print(f"Successfully sent {len(batch)} logs.")
            else:
                print(f"Failed! Status: {response.status_code}, Body: {response.text}")

        except Exception as e:
            print(f"Network error: {e}")

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))


if __name__ == "__main__":
    send_logs()
