"""POST correlation demo logs to OpenObserve _json API."""

from __future__ import annotations

import logging

import requests

from o2_correlation import config, scenarios

logger = logging.getLogger(__name__)


def send_logs(records: list[dict] | None = None) -> None:
    batch = records if records is not None else scenarios.all_log_batch()
    if not batch:
        return
    for stream_name in config.O2_LOG_STREAMS:
        url = config.logs_json_url(stream_name)
        response = requests.post(
            url,
            json=batch,
            auth=config.requests_auth(),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Log ingest failed stream={stream_name} status={response.status_code} "
                f"body={response.text[:500]}"
            )
        # OpenObserve returns {"code":200,"status":[{"name":"...","successful":N,"failed":0}]}
        try:
            body = response.json()
            statuses = body.get("status") or []
            failed = sum(int(s.get("failed") or 0) for s in statuses if isinstance(s, dict))
            if failed:
                raise RuntimeError(
                    f"Log ingest partial failure stream={stream_name} body={body}"
                )
        except ValueError:
            pass
        logger.debug("Ingested %s log records to stream=%s", len(batch), stream_name)
