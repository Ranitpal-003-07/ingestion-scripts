from __future__ import annotations

import os
import random
import string
import time
import uuid


REGIONS = ("us-east-1", "us-west-2", "eu-west-1", "ap-south-1", "ap-southeast-1")
AZS = {
    "us-east-1": ("us-east-1a", "us-east-1b", "us-east-1c"),
    "us-west-2": ("us-west-2a", "us-west-2b"),
    "eu-west-1": ("eu-west-1a", "eu-west-1b", "eu-west-1c"),
    "ap-south-1": ("ap-south-1a", "ap-south-1b"),
    "ap-southeast-1": ("ap-southeast-1a", "ap-southeast-1b"),
}
TENANTS = ("acme", "globex", "initech", "umbrella", "wayne")
FEATURE_FLAGS = ("checkout_v3", "search_v2", "auth_mfa", "payments_retry", "slow_auth_path")
EXPERIMENTS = ("exp_checkout_cta", "exp_search_rank", "exp_pay_wallet", "control")
USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 Version/17.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/128.0.6613.88 Mobile Safari/537.36",
    "okhttp/4.12.0 demo-android/3.4.1",
    "DemoIOS/4.2.0 (iPhone; iOS 17.6; Scale/3.00)",
)
CURRENCIES = ("USD", "EUR", "INR", "GBP")
PAYMENT_METHODS = ("card", "wallet", "netbanking", "upi", "apple_pay")
HTTP_FLAVORS = ("1.1", "2.0")
# Facet keys for CtrlB key/timestamp field tests.
SPAN_KEYS = (
    "checkout",
    "inventory",
    "payments",
    "orders",
    "auth",
    "search",
    "notify",
    "gateway",
    "cdn",
    "edge",
)


def new_trace_id() -> int:
    return int.from_bytes(os.urandom(16), "big")


def new_span_id() -> int:
    return int.from_bytes(os.urandom(8), "big")


def format_trace_id(trace_id: int) -> str:
    return format(trace_id, "032x")


def random_sku() -> str:
    return "SKU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def random_order_id() -> str:
    return "ord_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))


def random_customer_id() -> str:
    return "cust_" + "".join(random.choices(string.digits, k=8))


def random_session_id() -> str:
    return "sess_" + uuid.uuid4().hex[:16]


def random_request_id() -> str:
    return str(uuid.uuid4())


def random_message_id() -> str:
    return "msg-" + uuid.uuid4().hex[:20]


def random_aws_request_id() -> str:
    return str(uuid.uuid4())


def random_ip(private: bool = True) -> str:
    if private:
        return f"10.{random.randint(0, 31)}.{random.randint(1, 254)}.{random.randint(2, 250)}"
    return f"{random.randint(23, 203)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(2, 250)}"


def random_port() -> int:
    return random.choice((443, 8443, 8080, 9090, 5432, 3306, 6379, 27017, 9200, 50051))


def random_email(customer_id: str | None = None) -> str:
    suffix = customer_id or "".join(random.choices(string.digits, k=6))
    domain = random.choice(("acme.test", "shop.demo", "mail.example"))
    return f"user.{suffix}@{domain}"


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def random_region() -> str:
    return random.choice(REGIONS)


def random_az(region: str | None = None) -> str:
    region = region or random_region()
    return random.choice(AZS.get(region, ("us-east-1a",)))


def random_tenant() -> str:
    return random.choice(TENANTS)


def random_span_key() -> str:
    """CtrlB facet key — category + short id for cardinality."""
    return f"{random.choice(SPAN_KEYS)}-{uuid.uuid4().hex[:8]}"


def now_timestamp_us() -> int:
    """Wall-clock microseconds since epoch (CtrlB log-style timestamp)."""
    return int(time.time() * 1_000_000)


def random_currency() -> str:
    return random.choice(CURRENCIES)


def random_payment_method() -> str:
    return random.choice(PAYMENT_METHODS)


def random_amount_cents() -> int:
    return random.choice((499, 999, 1299, 2499, 4999, 8999, 14999))
