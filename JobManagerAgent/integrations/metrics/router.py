from __future__ import annotations

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from utils.agent_logger import get_agent_logger

from .gauges import get_last_collected_at


LOGGER = get_agent_logger(__name__)

router = APIRouter()


@router.get("/metrics")
def metrics(request: Request) -> Response:
    # One line per request -- the plainest way to confirm from JobManagerAgent's own logs that
    # Prometheus is actually reaching this endpoint (on top of checking Prometheus's own
    # /targets page). user_agent lets you tell a real Prometheus scrape ("Prometheus/x.y.z")
    # apart from a manual curl/browser hit; cache_age_seconds catches a stalled collector thread
    # even when the HTTP layer is otherwise fine.
    last_collected_at = get_last_collected_at()
    cache_age_seconds = f"{time.time() - last_collected_at:.1f}" if last_collected_at is not None else "n/a"
    LOGGER.info(
        "metrics_scraped client=%s user_agent=%s cache_age_seconds=%s",
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent", "unknown"),
        cache_age_seconds,
    )

    # generate_latest() reads the current value of the module-level Gauges (gauges.py) -- it
    # does not sample the OS. Freshness is entirely down to how often the background collector
    # (collector.py) last called update_metrics().
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
