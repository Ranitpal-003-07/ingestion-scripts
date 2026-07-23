"""Flask demo app — no OpenTelemetry imports.

Zero-code (CtrlB Flask guide):

    opentelemetry-instrument flask run -p 8080 --no-reload

Docker:

    opentelemetry-instrument python app.py
"""
import logging
import os
import random
import time

from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("flask_instrumentation_test")

app = Flask(__name__)


@app.get("/health")
def health():
    log.info("health check")
    return "ok\n", 200, {"Content-Type": "text/plain"}


@app.get("/roll")
def roll():
    value = random.randint(1, 6)
    log.info("dice.roll value=%s", value)
    return str(value), 200, {"Content-Type": "text/plain"}


@app.get("/work")
def work():
    log.info("work.request started")
    time.sleep(random.randint(20, 80) / 1000)
    time.sleep(random.randint(50, 200) / 1000)
    time.sleep(random.randint(30, 120) / 1000)
    log.info("work.request done")
    return jsonify({"status": "done"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    # use_reloader=False so Docker / opentelemetry-instrument stay on this process
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
