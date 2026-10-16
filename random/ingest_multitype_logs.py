"""
Ingest logs with mixed field datatypes to CtrlB via /_json_evolving.

Covers: string, bool, int, float, null, string/int/bool arrays, nested objects.
Add any extra fields by editing EXTRA_FIELDS below (or pass --extra-json).

Usage:
  python ingest_multitype_logs.py
  ENDPOINT=http://staging.ctrlb.dev:8080/api/default/my_stream/v2/_json_evolving \\
    LOGS_PER_SECOND=20 python ingest_multitype_logs.py
  python ingest_multitype_logs.py --extra-json '{"custom_flag": true, "score": 9.5}'
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from typing import Any

import requests

ENDPOINT = os.environ.get(
    "ENDPOINT",
    "http://staging.ctrlb.dev:8080/api/default/multitype_field_test/v2/_json_evolving",
)

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "User-Agent": "MultitypeLogIngest/1.0",
}

LOGS_PER_SECOND = int(os.environ.get("LOGS_PER_SECOND", "10"))

SERVICES = ["checkout-api", "search-api", "auth-service", "order-processor", "api-gateway"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]
LOG_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]
TAGS = ["billing", "auth", "cache", "db", "edge", "worker"]

# Edit this dict to inject any additional fields (any JSON-serializable type).
EXTRA_FIELDS: dict[str, Any] = {
    # "my_custom_string": "hello",
    # "my_custom_bool": True,
    # "my_custom_int": 42,
    # "my_custom_float": 3.14,
    # "my_custom_list": ["a", 1, True],
    # "my_custom_obj": {"nested": True},
}

_log_counter = 0


def generate_log(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one log record with fields of many JSON datatypes."""
    global _log_counter

    now_us = int(time.time() * 1_000_000)
    service = SERVICES[_log_counter % len(SERVICES)]
    region = REGIONS[_log_counter % len(REGIONS)]
    idx = _log_counter
    _log_counter += 1

    # --- core identity / timestamps (int) ---
    log: dict[str, Any] = {
        "_timestamp": now_us,
        "timestamp": now_us,
        "ctrlb_timestamp": now_us,
        "service": service,
        "region": region,
        "environment": "staging",
        "message": f"multitype ingest sample #{idx}",
        "body": f"multitype ingest sample #{idx}",
        "log_level": random.choice(LOG_LEVELS),
        "trace_id": f"tr-{random.randint(1, 0xFFFFFFFF):08x}",
        "span_id": f"sp-{random.randint(1, 0xFFFF):04x}",
        "host": f"{service}-{random.randint(1000, 9999)}",
    }

    # --- string ---
    log["request_id"] = f"req-{random.randint(1, 99999999):08d}"
    log["http_method"] = random.choice(["GET", "POST", "PUT", "DELETE", "PATCH"])
    log["path"] = random.choice(["/api/v1/orders", "/api/v2/users", "/health", "/checkout"])
    log["user_agent"] = "MultitypeLogIngest/1.0"

    # --- bool ---
    log["is_error"] = random.choice([True, False])
    log["is_retry"] = random.random() < 0.2
    log["authenticated"] = random.choice([True, False])
    log["cache_hit"] = random.choice([True, False])
    log["feature_flag_enabled"] = random.choice([True, False])

    # --- int ---
    log["status_code"] = random.choice([200, 201, 204, 400, 401, 404, 500, 502, 503])
    log["request_count"] = random.randint(1, 100)
    log["active_connections"] = random.randint(1, 500)
    log["retry_count"] = random.randint(0, 5)
    log["http_status_family"] = log["status_code"] // 100
    log["sequence"] = idx

    # --- float ---
    log["latency_ms"] = round(random.uniform(0.5, 2500.0), 3)
    log["cpu_pct"] = round(random.uniform(0.0, 100.0), 2)
    log["memory_usage_gb"] = round(random.uniform(0.1, 64.0), 4)
    log["error_rate_pct"] = round(random.uniform(0.0, 15.0), 2)
    log["throughput_mbps"] = round(random.uniform(0.01, 999.99), 2)
    log["score"] = round(random.uniform(-1.0, 1.0), 6)

    # --- null (JSON null) ---
    log["optional_note"] = None if random.random() < 0.5 else f"note-{idx}"
    log["deleted_at"] = None

    # --- arrays ---
    log["tags"] = random.sample(TAGS, k=random.randint(1, 3))  # string[]
    log["status_history"] = [random.choice([200, 201, 400, 500]) for _ in range(random.randint(1, 4))]  # int[]
    log["flag_bits"] = [random.choice([True, False]) for _ in range(3)]  # bool[]
    log["latency_samples_ms"] = [round(random.uniform(1.0, 100.0), 2) for _ in range(4)]  # float[]
    log["mixed_array"] = [
        "ok",
        random.randint(1, 99),
        random.choice([True, False]),
        round(random.uniform(0.1, 9.9), 2),
        None,
    ]

    # --- nested object ---
    log["http"] = {
        "method": log["http_method"],
        "path": log["path"],
        "status": log["status_code"],
        "success": log["status_code"] < 400,
        "bytes_in": random.randint(0, 50_000),
        "bytes_out": random.randint(0, 200_000),
        "headers": {
            "content_type": "application/json",
            "x_request_id": log["request_id"],
        },
    }
    log["geo"] = {
        "country": random.choice(["IN", "US", "GB", "DE", "JP"]),
        "lat": round(random.uniform(-90.0, 90.0), 5),
        "lon": round(random.uniform(-180.0, 180.0), 5),
        "vpn": random.choice([True, False]),
    }
    log["metrics"] = {
        "counters": {"hits": random.randint(0, 1000), "misses": random.randint(0, 200)},
        "gauges": {"qps": round(random.uniform(1.0, 500.0), 1)},
        "labels": random.sample(TAGS, k=2),
    }

    # Merge static EXTRA_FIELDS then any CLI/runtime extras (extras win).
    if EXTRA_FIELDS:
        log.update(EXTRA_FIELDS)
    if extra:
        log.update(extra)

    return log


def send_logs(extra: dict[str, Any] | None = None) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)

    print(
        f"Starting multitype log ingestion ({LOGS_PER_SECOND} logs/sec)\n"
        f"  endpoint: {ENDPOINT}\n"
        f"  types: string, bool, int, float, null, arrays, nested objects"
    )
    if EXTRA_FIELDS or extra:
        print(f"  extra fields: {list({**(EXTRA_FIELDS or {}), **(extra or {})})}")

    while True:
        start = time.time()
        batch = [generate_log(extra) for _ in range(LOGS_PER_SECOND)]

        try:
            resp = session.post(ENDPOINT, json=batch, timeout=10)
            print(f"Status: {resp.status_code}  sent={len(batch)}")
            if resp.status_code != 200:
                print("Response:", resp.text[:500])
        except Exception as e:
            print("Error sending logs:", e)

        time.sleep(max(0.0, 1.0 - (time.time() - start)))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest multitype JSON logs to CtrlB /_json_evolving")
    p.add_argument(
        "--endpoint",
        default=ENDPOINT,
        help="Full ingest URL (default: ENDPOINT env or staging .../v2/_json_evolving)",
    )
    p.add_argument(
        "--rate",
        type=int,
        default=LOGS_PER_SECOND,
        help="Logs per second (default: LOGS_PER_SECOND env or 10)",
    )
    p.add_argument(
        "--extra-json",
        default="",
        help='JSON object of extra fields to merge into every log, e.g. \'{"foo": true}\'',
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Send a single batch and exit (useful for smoke tests)",
    )
    return p.parse_args()


def main() -> None:
    global ENDPOINT, LOGS_PER_SECOND

    args = parse_args()
    ENDPOINT = args.endpoint
    LOGS_PER_SECOND = args.rate

    extra: dict[str, Any] = {}
    if args.extra_json.strip():
        parsed = json.loads(args.extra_json)
        if not isinstance(parsed, dict):
            raise SystemExit("--extra-json must be a JSON object")
        extra = parsed

    if args.once:
        session = requests.Session()
        session.headers.update(HEADERS)
        batch = [generate_log(extra) for _ in range(LOGS_PER_SECOND)]
        # Print one sample so you can verify types before/after ingest
        print("Sample log:")
        print(json.dumps(batch[0], indent=2, default=str))
        resp = session.post(ENDPOINT, json=batch, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print("Response:", resp.text[:500])
        return

    send_logs(extra)


if __name__ == "__main__":
    main()
