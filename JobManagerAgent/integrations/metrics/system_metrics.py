from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import psutil

from utils.env_utils import load_env_value


def get_disk_path() -> str:
    configured = load_env_value("METRICS_DISK_PATH", "").strip()
    if configured:
        return configured
    # Path.cwd().anchor resolves to the right thing on both platforms this agent runs on --
    # "C:\\" for local Windows dev, "/" for the Linux Railway deployment -- unlike a hardcoded
    # "/", which psutil.disk_usage() rejects outright on Windows.
    return Path.cwd().anchor


def collect_system_metrics() -> dict[str, Any]:
    """One-off snapshot of CPU/memory/disk/network. Deliberately has no Prometheus/Gauge
    dependency (those live in gauges.py) so this module -- and its `python -m
    integrations.metrics.system_metrics` CLI entrypoint below -- can be imported and re-run as
    __main__ without re-registering anything against prometheus_client's global registry.
    """
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count(logical=True) or 0

    memory = psutil.virtual_memory()

    disk_path = get_disk_path()
    disk = psutil.disk_usage(disk_path)

    network = psutil.net_io_counters()

    return {
        "collected_at": time.time(),
        "cpu": {"usage_percent": cpu_percent, "count": cpu_count},
        "memory": {"used_bytes": memory.used, "total_bytes": memory.total, "usage_percent": memory.percent},
        "disk": {"path": disk_path, "used_bytes": disk.used, "total_bytes": disk.total, "usage_percent": disk.percent},
        "network": {"bytes_sent": network.bytes_sent, "bytes_received": network.bytes_recv},
    }


if __name__ == "__main__":
    # Manual CLI entrypoint: `python -m integrations.metrics.system_metrics` (run from the
    # JobManagerAgent directory) -- prints one snapshot without touching the API process, the
    # background collector thread, or the Prometheus Gauges.
    print(json.dumps(collect_system_metrics(), indent=2))
