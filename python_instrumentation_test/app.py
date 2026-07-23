"""Minimal HTTP app — no OpenTelemetry imports.

Run with zero-code auto-instrumentation:

    opentelemetry-instrument python3 app.py
"""
import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path == "/health":
            self._write(200, "ok\n")
        elif self.path == "/roll":
            self._roll()
        elif self.path == "/work":
            self._work()
        else:
            self._write(404, "not found\n")

    def _roll(self):
        value = random.randint(1, 6)
        self._write(200, str(value))

    def _work(self):
        simulate_step(20, 80)
        simulate_step(50, 200)
        simulate_step(30, 120)
        self._write(200, json.dumps({"status": "done"}) + "\n", "application/json")

    def _write(self, status, body, content_type="text/plain"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def simulate_step(min_ms, max_ms):
    time.sleep(random.randint(min_ms, max_ms) / 1000)


def main():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("", port), Handler)
    print(f"python_instrumentation_test listening on http://localhost:{port}")
    print("  GET /health  — liveness")
    print("  GET /roll    — random 1-6")
    print("  GET /work    — simulated latency")
    print("  (no OTEL in code — use: opentelemetry-instrument python3 app.py)")
    server.serve_forever()


if __name__ == "__main__":
    main()
