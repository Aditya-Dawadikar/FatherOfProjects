from __future__ import annotations

from typing import Literal


GuardrailCategory = Literal["output_validation", "injection", "tool_usage"]


class GuardrailBlockedError(RuntimeError):
	"""Raised when a guardrail check rejects an LLM scoring response, a scraped job posting, or a
	tool call that violates the ReAct agent's tool-usage contract.

	Carries enough structure (guardrail name, category, the job_id it concerns) for the catch site
	-- guardrails/middleware.py's wrap_tool_call, or an eval harness -- to record the trigger
	(guardrails/report.py) or score it against a golden dataset without re-parsing the message.
	"""

	def __init__(self, *, guardrail: str, category: GuardrailCategory, reason: str, job_id: int | None = None) -> None:
		super().__init__(reason)
		self.guardrail = guardrail
		self.category: GuardrailCategory = category
		self.reason = reason
		self.job_id = job_id
