from __future__ import annotations

import time

from utils.agent_logger import get_agent_logger
from utils.config import DEFAULT_METRICS_COLLECTION_INTERVAL_SECONDS
from utils.env_utils import load_env_value

from .gauges import update_metrics


LOGGER = get_agent_logger(__name__)


def load_collection_interval_seconds() -> float:
    return float(load_env_value("METRICS_COLLECTION_INTERVAL_SECONDS", str(DEFAULT_METRICS_COLLECTION_INTERVAL_SECONDS)))


def run_metrics_collector(interval_seconds: float | None = None) -> None:
    """Runs forever on its own daemon thread (started in api/app.py's lifespan): refreshes the
    CPU/memory/disk/network Gauges on a fixed interval so GET /metrics never has to touch the OS
    itself -- it only serves whatever this loop last collected.
    """
    interval = interval_seconds if interval_seconds is not None else load_collection_interval_seconds()
    LOGGER.info("Starting system metrics collector interval_seconds=%.1f", interval)

    while True:
        try:
            update_metrics()
        except Exception:
            LOGGER.exception("System metrics collection failed; will retry next interval")
        time.sleep(interval)
