from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    # generate_latest() reads the current value of the module-level Gauges (system_metrics.py) --
    # it does not sample the OS. Freshness is entirely down to how often the background collector
    # (collector.py) last called update_metrics().
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
