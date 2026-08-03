from __future__ import annotations

from prometheus_client import Gauge

from .system_metrics import collect_system_metrics


# Namespaced so this agent's gauges don't collide with other services' metrics once Prometheus
# scrapes more than one target (see Observability/prometheus/prometheus.yml).
_PREFIX = "jobmanageragent"

CPU_USAGE_PERCENT = Gauge(f"{_PREFIX}_cpu_usage_percent", "CPU utilization percent, averaged across all logical cores")
CPU_COUNT = Gauge(f"{_PREFIX}_cpu_count", "Number of logical CPU cores available to the process")
MEMORY_USED_BYTES = Gauge(f"{_PREFIX}_memory_used_bytes", "Resident memory in use, in bytes")
MEMORY_TOTAL_BYTES = Gauge(f"{_PREFIX}_memory_total_bytes", "Total physical memory, in bytes")
MEMORY_USAGE_PERCENT = Gauge(f"{_PREFIX}_memory_usage_percent", "Memory utilization percent")
DISK_USED_BYTES = Gauge(f"{_PREFIX}_disk_used_bytes", "Disk space in use at the sampled path, in bytes")
DISK_TOTAL_BYTES = Gauge(f"{_PREFIX}_disk_total_bytes", "Total disk capacity at the sampled path, in bytes")
DISK_USAGE_PERCENT = Gauge(f"{_PREFIX}_disk_usage_percent", "Disk utilization percent at the sampled path")
NETWORK_BYTES_SENT = Gauge(f"{_PREFIX}_network_bytes_sent_total", "Bytes sent over all network interfaces since boot")
NETWORK_BYTES_RECEIVED = Gauge(f"{_PREFIX}_network_bytes_received_total", "Bytes received over all network interfaces since boot")
LAST_COLLECTED_TIMESTAMP = Gauge(f"{_PREFIX}_metrics_last_collected_timestamp_seconds", "Unix timestamp when these gauges were last refreshed")


def update_metrics() -> None:
    """Refreshes the module-level Gauges from a fresh OS sample. Called on an interval by the
    background collector thread (see collector.py) -- never from the /metrics request handler
    itself, which only reads whatever these Gauges were last set to.
    """
    snapshot = collect_system_metrics()

    CPU_USAGE_PERCENT.set(snapshot["cpu"]["usage_percent"])
    CPU_COUNT.set(snapshot["cpu"]["count"])

    MEMORY_USED_BYTES.set(snapshot["memory"]["used_bytes"])
    MEMORY_TOTAL_BYTES.set(snapshot["memory"]["total_bytes"])
    MEMORY_USAGE_PERCENT.set(snapshot["memory"]["usage_percent"])

    DISK_USED_BYTES.set(snapshot["disk"]["used_bytes"])
    DISK_TOTAL_BYTES.set(snapshot["disk"]["total_bytes"])
    DISK_USAGE_PERCENT.set(snapshot["disk"]["usage_percent"])

    NETWORK_BYTES_SENT.set(snapshot["network"]["bytes_sent"])
    NETWORK_BYTES_RECEIVED.set(snapshot["network"]["bytes_received"])

    LAST_COLLECTED_TIMESTAMP.set(snapshot["collected_at"])
