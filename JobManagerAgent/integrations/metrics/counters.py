from __future__ import annotations

from prometheus_client import Counter


# Namespaced the same way gauges.py's Gauges are (see its _PREFIX comment) -- kept as a local
# constant rather than imported from there since these are two independent, self-contained metric
# modules that both happen to publish under the same agent namespace.
_PREFIX = "jobmanageragent"

GUARDRAILS_TRIGGERED_TOTAL = Counter(
	f"{_PREFIX}_guardrails_triggered_total",
	"Count of guardrail triggers, by guardrail name and category",
	labelnames=("guardrail", "category"),
)
