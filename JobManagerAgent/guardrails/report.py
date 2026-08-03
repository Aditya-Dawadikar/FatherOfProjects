from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from integrations.metrics.counters import GUARDRAILS_TRIGGERED_TOTAL
from shared.guardrail_data import GuardrailTrigger
from utils.agent_logger import get_agent_logger


LOGGER = get_agent_logger(__name__)


def record_guardrail_trigger(
	*,
	engine: Engine,
	guardrail: str,
	category: str,
	reason: str,
	job_id: int | None = None,
) -> None:
	"""Single choke point for tracking a guardrail trigger: increments the
	jobmanageragent_guardrails_triggered_total Prometheus counter and writes a durable audit row
	to the guardrail_triggers table. Every guardrail catch site -- guardrails/middleware.py's
	wrap_tool_call, and the ToolCallLimitExceededError handler in agents/react_agent.py -- calls
	this instead of tracking triggers itself, so the counter and the audit table can never drift
	apart from what the agent actually blocked.
	"""
	GUARDRAILS_TRIGGERED_TOTAL.labels(guardrail=guardrail, category=category).inc()
	with Session(engine) as session:
		session.add(GuardrailTrigger(job_id=job_id, guardrail=guardrail, category=category, reason=reason))
		session.commit()
	LOGGER.action("guardrail_triggered", guardrail=guardrail, category=category, job_id=job_id, reason=reason)
