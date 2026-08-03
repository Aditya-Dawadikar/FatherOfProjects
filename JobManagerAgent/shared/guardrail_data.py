from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.job_data import Base
from utils.config import DEFAULT_GUARDRAIL_TRIGGER_TABLE_NAME


def load_guardrail_trigger_table_name() -> str:
	return os.getenv("GUARDRAIL_TRIGGER_TABLE_NAME", DEFAULT_GUARDRAIL_TRIGGER_TABLE_NAME).strip() or DEFAULT_GUARDRAIL_TRIGGER_TABLE_NAME


class GuardrailTrigger(Base):
	"""Durable audit log of every guardrail trigger, alongside the jobmanageragent_guardrails_
	triggered_total Prometheus counter (integrations/metrics/counters.py) -- the counter answers
	"how often", this table answers "which job, which guardrail, why". Both are written together
	by guardrails/report.py's record_guardrail_trigger(), never independently."""

	__tablename__ = load_guardrail_trigger_table_name()

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	# Nullable: a tool-usage guardrail like tool_call_limit_exceeded fires at the cycle level, not
	# tied to any single job_id.
	job_id: Mapped[int | None] = mapped_column(Integer)
	guardrail: Mapped[str] = mapped_column(String(100), nullable=False)
	category: Mapped[str] = mapped_column(String(50), nullable=False)
	reason: Mapped[str] = mapped_column(Text, nullable=False)
	triggered_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=False),
		default=datetime.utcnow,
		nullable=False,
	)
