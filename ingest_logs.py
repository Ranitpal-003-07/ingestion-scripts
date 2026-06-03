import requests
import time
import random

# Endpoint
ENDPOINT = "http://staging.ctrlb.dev:8080/api/default/object_table_bug/v3/_json_evolving"

# Headers
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "MetricsGenerator/1.0"
}

LOGS_PER_SECOND = 100

ACTIONS = ["ALLOW", "BLOCK", "COUNT"]
HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
URIS = [
    "/api/v1/cart",
    "/api/v1/login",
    "/api/v1/checkout",
    "/api/v2/products",
    "/api/v2/users/profile",
    "/api/v1/search",
]
COUNTRIES = ["IN", "US", "GB", "DE", "JP", "AU", "BR"]
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
]
TERMINATING_RULES = [
    "CrossSiteScripting_BODY",
    "SQLInjection_QUERYSTRING",
    "SizeRestrictions_BODY",
    "GenericLFI_BODY",
    "RestrictedExtensions_URIPATH",
]
NON_TERMINATING_RULES = [
    "SizeRestrictions_BODY",
    "NoUserAgent_HEADER",
    "UserAgent_BadBots_HEADER",
    "EC2MetaDataSSRF_BODY",
]
CONDITION_TYPES = ["XSS", "SQL_INJECTION", "LFI", "RFI", "SIZE_RESTRICTION"]
LOCATIONS = ["BODY", "QUERYSTRING", "HEADER", "URIPATH", "COOKIE"]
SENSITIVITY_LEVELS = ["LOW", "MEDIUM", "HIGH"]
THREAT_INDICATORS = [
    ("disposable_email", "temp-mail.org"),
    ("disposable_email", "guerrillamail.com"),
    ("credential_stuffing", "high_velocity"),
    ("credential_stuffing", "known_breach_list"),
    ("bot_traffic", "datacenter_ip"),
    ("bot_traffic", "headless_browser"),
]
DISPOSABLE_EMAILS = ["temp-mail.org", "guerrillamail.com", "mailinator.com"]
WEBACL_ID = "arn:aws:wafv2:us-east-1:123456789012:global/webacl/prod-acl/abc123"
RULE_GROUP_ID = "arn:aws:wafv2:us-east-1:123456789012:global/rulegroup/CommonRuleSet/def456"
RATE_RULE_ID = "arn:aws:wafv2:us-east-1:123456789012_MANAGED:global/ipset/0626fa64"


def make_header(name, value):
    return {"name": name, "value": value}


def random_ip():
    return f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def random_hex(length):
    return "".join(random.choice("0123456789abcdef") for _ in range(length))


def make_http_request():
    req_id = f"req-{random.randint(1, 99999999):08d}"
    headers = [
        make_header("host", "api-gateway.example.com"),
        make_header("user-agent", random.choice(USER_AGENTS)),
        make_header("content-type", "application/json"),
    ]
    if random.random() > 0.5:
        headers.append(make_header("x-forwarded-for", random_ip()))
    if random.random() > 0.5:
        headers.append(make_header("accept", "application/json"))

    return {
        "args": random.choice(["", "page=1&limit=20", "q=test&sort=desc"]),
        "clientip": random_ip(),
        "country": random.choice(COUNTRIES),
        "headers": headers,
        "httpmethod": random.choice(HTTP_METHODS),
        "httpversion": random.choice(["HTTP/1.1", "HTTP/2.0"]),
        "requestid": req_id,
        "uri": random.choice(URIS),
    }


def make_rate_rule():
    return {
        "limitkey": random.choice(["IP", "CUSTOMKEYS", "FORWARDED_IP"]),
        "maxrateallowed": random.choice([100, 500, 1200, 2000]),
        "ratebasedruleid": RATE_RULE_ID,
    }


def make_rule_match_detail():
    condition = random.choice(CONDITION_TYPES)
    matched_data = {
        "XSS": ["<script>", "javascript:", "onerror="],
        "SQL_INJECTION": ["' OR 1=1--", "UNION SELECT", "DROP TABLE"],
        "LFI": ["../../etc/passwd", "/proc/self/environ"],
        "RFI": ["http://evil.com/shell.txt"],
        "SIZE_RESTRICTION": ["payload_too_large"],
    }
    return {
        "conditiontype": condition,
        "location": random.choice(LOCATIONS),
        "matcheddata": [random.choice(matched_data[condition])],
        "sensitivitylevel": random.choice(SENSITIVITY_LEVELS),
    }


def make_non_terminating_rule():
    threat_name, threat_details = random.choice(THREAT_INDICATORS)
    solve_ts = str(int(time.time()) - random.randint(0, 3600))
    return {
        "accountcreationfraudprevention": {
            "action": random.choice(ACTIONS),
            "creationresult": random.choice(["FAILED", "SUCCESS", "PENDING"]),
            "threatindicators": [
                {
                    "details": random.choice(DISPOSABLE_EMAILS),
                    "name": "disposable_email",
                }
            ],
        },
        "accounttakeoverprevention": {
            "action": random.choice(ACTIONS),
            "loginresult": random.choice(["FAILED", "SUCCESS"]),
            "threatindicators": [
                {
                    "details": threat_details,
                    "name": threat_name,
                }
            ],
        },
        "action": random.choice(ACTIONS),
        "captcharesponse": {
            "responsecode": random.choice(["200", "405", "503"]),
            "solvetimestamp": str(int(solve_ts) + 1),
        },
        "challengeresponse": {
            "responsecode": random.choice(["200", "202", "403"]),
            "solvetimestamp": solve_ts,
        },
        "ruleid": random.choice(NON_TERMINATING_RULES),
        "rulematchdetails": [make_rule_match_detail()] if random.random() > 0.5 else [],
    }


def make_rule_group():
    return {
        "nonterminatingmatchingrules": [make_non_terminating_rule()],
        "rulegroupid": RULE_GROUP_ID,
        "terminatingrule": {
            "action": random.choice(["BLOCK", "ALLOW", "COUNT"]),
            "ruleid": random.choice(TERMINATING_RULES),
            "rulematchdetails": [make_rule_match_detail()],
        },
    }


def generate_waf_match():
    now_us = int(time.time() * 1_000_000)
    terminating_rule = random.choice(TERMINATING_RULES)

    return {
        "action": random.choice(ACTIONS),
        "ctrlb_log_level": "UNKNOWN",
        "ctrlb_timestamp": now_us,
        "formatversion": 1,
        "httprequest": make_http_request(),
        "httpsourceid": random_hex(8).upper() + random_hex(7).upper(),
        "httpsourcename": random.choice(["CF", "ALB", "APIGW", "CLOUDFRONT"]),
        "ja3fingerprint": random_hex(8),
        "ja4fingerprint": f"t13d{random.randint(1000, 9999)}h2_{random.randint(10, 99)}_{random.randint(100000, 999999)}",
        "labels": [],
        "nonterminatingmatchingrules": [],
        "ratebasedrulelist": [make_rate_rule()],
        "requestheadersinserted": [],
        "rulegrouplist": [make_rule_group()],
        "terminatingruleid": random.choice(["Default_Action", terminating_rule]),
        "terminatingrulematchdetails": [],
        "terminatingruletype": random.choice(["REGULAR", "RATE_BASED", "MANAGED_RULE_GROUP"]),
        "timestamp": now_us,
        "webaclid": WEBACL_ID,
        # numeric fields for int/float type testing
        "request_count": random.randint(1, 100),
        "active_connections": random.randint(10, 500),
        "cpu_cores_in_use": random.randint(1, 16),
        "latency_ms": round(random.uniform(5.0, 250.0), 2),
        "memory_usage_gb": round(random.uniform(0.5, 12.0), 3),
        "error_rate_pct": round(random.uniform(0.0, 5.0), 2),
        "throughput_mbps": round(random.uniform(10.5, 1000.8), 1),
        "disk_io_utilization": round(random.uniform(0.0, 100.0), 2),
    }


def send_metrics():
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"Starting WAF nested log ingestion ({LOGS_PER_SECOND} records/sec)...")

    while True:
        start_time = time.time()

        batch = [generate_waf_match() for _ in range(LOGS_PER_SECOND)]

        try:
            response = session.post(
                ENDPOINT,
                json=batch,
                timeout=5
            )

            if response.status_code == 200:
                print(f"Successfully sent {len(batch)} WAF match records.")
            else:
                print(f"Failed! Status: {response.status_code}, Body: {response.text}")

        except Exception as e:
            print(f"Network error: {e}")

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))


if __name__ == "__main__":
    send_metrics()
