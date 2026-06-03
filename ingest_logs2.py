import requests
import time

# Endpoint
ENDPOINT = "http://staging.ctrlb.dev:8080/api/default/escape_table_bug/_json_evolving"

# Headers (matching Postman)
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "User-Agent": "PostmanRuntime/7.51.0"
}

LOGS_PER_SECOND = 30

# Real tab (\t) vs real newline (\n) only — no literal "\\t"/"\\n" text variants
ESCAPE_TEST_VARIANTS = [
    {
        "variant": "tab_only",
        "message": "colA\tcolB\tcolC\tcolD",
        "escape_test_field": "name\tage\tcity\tcountry",
    },
    {
        "variant": "newline_only",
        "message": "line one\nline two\nline three",
        "escape_test_field": "first row\nsecond row\nthird row",
    },
    {
        "variant": "spaces_vs_tab",
        "message": "with spaces: colA colB colC | with tabs: colA\tcolB\tcolC",
        "escape_test_field": "space separated values here",
    },
    {
        "variant": "tab_table_rows",
        "message": "header1\theader2\theader3\nval1\tval2\tval3\nval4\tval5\tval6",
        "escape_test_field": "id\tname\tstatus\n1\talice\tok\n2\tbob\tfail",
    },
    {
        "variant": "newline_paragraph",
        "message": "Paragraph one line.\n\nParagraph two after blank line.\n\nParagraph three.",
        "escape_test_field": "error: connection refused\nretrying in 5s\nconnected",
    },
]

_log_counter = 0


def generate_log():
    global _log_counter

    variant = ESCAPE_TEST_VARIANTS[_log_counter % len(ESCAPE_TEST_VARIANTS)]
    _log_counter += 1

    now_us = int(time.time() * 1_000_000)

    return {
        "_timestamp": now_us,
        "timestamp": now_us,
        "body": variant["message"],
        "escape_test_variant": variant["variant"],
        "escape_test_field": variant["escape_test_field"],
    }


def send_logs():
    session = requests.Session()
    session.headers.update(HEADERS)

    print(
        f"Starting flat escape-char log ingestion ({LOGS_PER_SECOND} logs/sec) "
        f"with real tab vs newline rendering test variants..."
    )

    while True:
        start_time = time.time()

        batch = [generate_log() for _ in range(LOGS_PER_SECOND)]

        try:
            response = session.post(
                ENDPOINT,
                json=batch,
                timeout=10
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
