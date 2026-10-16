"""Ingest logs into staging engine dataset `dataset_without_timestamp_1111`.

Records intentionally omit _timestamp / timestamp / ctrlb_timestamp.

Usage:
  python ingest_dataset_without_timestamp.py
  LOGS_PER_SECOND=20 python ingest_dataset_without_timestamp.py --once
"""

from __future__ import annotations

import argparse
import os
import random
import time

import requests

ENDPOINT = os.environ.get(
    "ENDPOINT",
    "https://staging.ctrlb.dev/engine/api/default/dataset_without_timestamp_1111/_json_evolving",
)

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "DatasetWithoutTimestampIngest/1.0",
}
LOGS_PER_SECOND = int(os.environ.get("LOGS_PER_SECOND", "10"))

SERVICES = ["checkout-api", "search-api", "auth-service", "order-processor", "api-gateway"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]
LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]
METHODS = ["GET", "POST", "PUT", "DELETE"]
PATHS = ["/api/v1/orders", "/api/v2/users", "/health", "/checkout", "/login"]


def generate_log(idx: int) -> dict:
    service = SERVICES[idx % len(SERVICES)]
    status = random.choice([200, 201, 400, 401, 404, 500, 502, 503])
    return {
        "service": service,
        "region": REGIONS[idx % len(REGIONS)],
        "environment": "staging",
        "log_level": random.choice(LEVELS),
        "message": f"ingest without timestamp sample #{idx}",
        "body": f"ingest without timestamp sample #{idx}",
        "request_id": f"req-{random.randint(1, 99_999_999):08d}",
        "http_method": random.choice(METHODS),
        "path": random.choice(PATHS),
        "status_code": status,
        "latency_ms": round(random.uniform(5.0, 1200.0), 2),
        "is_error": status >= 400,
        "host": f"{service}-{random.randint(1000, 9999)}",
        "trace_id": f"tr-{random.randint(1, 0xFFFFFFFF):08x}",
    }


def send_batch(batch: list[dict]) -> None:
    r = requests.post(ENDPOINT, headers=HEADERS, json=batch, timeout=10)
    print(f"sent={len(batch)} status={r.status_code} body={r.text[:120]!r}")
    r.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Send one batch then exit")
    args = parser.parse_args()

    print(f"endpoint={ENDPOINT} logs_per_second={LOGS_PER_SECOND}")
    idx = 0
    while True:
        batch = [generate_log(idx + i) for i in range(LOGS_PER_SECOND)]
        idx += LOGS_PER_SECOND
        send_batch(batch)
        if args.once:
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
