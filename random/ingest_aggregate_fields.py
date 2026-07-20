import random
import time

import requests

ENDPOINT = "http://staging.ctrlb.dev:8080/api/default/aggregate_field_test/_json_evolving"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "User-Agent": "PostmanRuntime/7.51.0",
}

LOGS_PER_SECOND = 10

SERVICES = ["checkout-api", "search-api", "auth-service", "order-processor", "api-gateway"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]
ENVIRONMENT = "staging"

# Field names are literal aggregate expressions (with and without log. prefix).
AGGREGATE_FIELD_NAMES = [
    "min(_timestamp)",
    "max(_timestamp)",
    "min(log._timestamp)",
    "max(log._timestamp)",
    "avg(log.latency_ms)",
    "sum(log.latency_ms)",
    "min(log.latency_ms)",
    "max(log.latency_ms)",
    "sum(log.request_count)",
    "count(*)",
    "count_distinct(log.status_code)",
    "min(log.error_rate_pct)",
    "max(log.error_rate_pct)",
    "avg(log.error_rate_pct)",
    "max(log.throughput_mbps)",
    "min(log.throughput_mbps)",
    "sum(log.active_connections)",
]

_log_counter = 0


def build_aggregate_fields(
    now_us: int,
    latency_ms: float,
    request_count: int,
    status_code: int,
    error_rate_pct: float,
    throughput_mbps: float,
    active_connections: int,
) -> dict:
    ts_spread = random.randint(10_000, 500_000)
    group_size = random.randint(2, 25)

    return {
        "min(_timestamp)": now_us - ts_spread,
        "max(_timestamp)": now_us + ts_spread,
        "min(log._timestamp)": now_us - ts_spread * 2,
        "max(log._timestamp)": now_us + ts_spread * 2,
        "avg(log.latency_ms)": latency_ms,
        "sum(log.latency_ms)": round(latency_ms * group_size, 2),
        "min(log.latency_ms)": round(latency_ms * random.uniform(0.2, 0.8), 2),
        "max(log.latency_ms)": round(latency_ms * random.uniform(1.2, 2.5), 2),
        "sum(log.request_count)": request_count * group_size,
        "count(*)": group_size,
        "count_distinct(log.status_code)": random.randint(1, 6),
        "min(log.error_rate_pct)": round(error_rate_pct * random.uniform(0.1, 0.7), 2),
        "max(log.error_rate_pct)": round(error_rate_pct * random.uniform(1.1, 2.0), 2),
        "avg(log.error_rate_pct)": error_rate_pct,
        "max(log.throughput_mbps)": throughput_mbps,
        "min(log.throughput_mbps)": round(throughput_mbps * random.uniform(0.1, 0.6), 1),
        "sum(log.active_connections)": active_connections * group_size,
    }


def generate_log():
    global _log_counter

    service = SERVICES[_log_counter % len(SERVICES)]
    region = REGIONS[_log_counter % len(REGIONS)]
    group_id = f"{service}-{region}-{_log_counter // len(AGGREGATE_FIELD_NAMES) % 5}"

    now_us = int(time.time() * 1_000_000)
    timestamp_offset_us = (_log_counter % 10) * 50_000

    latency_ms = round(random.uniform(5.0, 2500.0), 2)
    request_count = random.randint(1, 50)
    status_code = random.choice([200, 201, 400, 401, 404, 500, 502, 503])
    error_rate_pct = round(random.uniform(0.0, 15.0), 2)
    throughput_mbps = round(random.uniform(1.0, 999.9), 1)
    active_connections = random.randint(1, 500)

    highlighted_field = AGGREGATE_FIELD_NAMES[_log_counter % len(AGGREGATE_FIELD_NAMES)]
    _log_counter += 1

    log = {
        "_timestamp": now_us - timestamp_offset_us,
        "timestamp": now_us - timestamp_offset_us,
        "ctrlb_timestamp": now_us,
        "service": service,
        "region": region,
        "environment": ENVIRONMENT,
        "group_id": group_id,
        "message": f"Aggregate field test — highlighted: {highlighted_field}",
        "body": f"Aggregate field test — highlighted: {highlighted_field}",
        "log_level": random.choice(["INFO", "WARN", "ERROR"]),
        "status_code": status_code,
        "latency_ms": latency_ms,
        "request_count": request_count,
        "active_connections": active_connections,
        "error_rate_pct": error_rate_pct,
        "throughput_mbps": throughput_mbps,
        "trace_id": f"tr-{random.randint(1, 99999999):08x}",
    }
    log.update(
        build_aggregate_fields(
            now_us,
            latency_ms,
            request_count,
            status_code,
            error_rate_pct,
            throughput_mbps,
            active_connections,
        )
    )
    return log


def send_logs():
    session = requests.Session()
    session.headers.update(HEADERS)

    print(
        f"Starting aggregate field log ingestion ({LOGS_PER_SECOND} logs/sec) "
        f"with {len(AGGREGATE_FIELD_NAMES)} expression field names..."
    )

    while True:
        start_time = time.time()

        batch = [generate_log() for _ in range(LOGS_PER_SECOND)]

        try:
            response = session.post(
                ENDPOINT,
                json=batch,
                timeout=10,
            )

            print(f"Status: {response.status_code}")

            if response.status_code != 200:
                print("Response:", response.text)

        except Exception as e:
            print("Error sending logs:", e)

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))


if __name__ == "__main__":
    send_logs()
