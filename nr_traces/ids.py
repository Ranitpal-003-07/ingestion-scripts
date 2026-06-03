import os
import random
import string


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
