from __future__ import annotations

from utils.config import GUARDRAIL_MAX_REASONING_CHARS

from .errors import GuardrailBlockedError


def check_output(*, job_id: int | None, match_score: int, reasoning: str) -> None:
	"""Rejects an LLM scoring response that doesn't look like a real evaluation of the job/resume:
	an empty reasoning field (most plausibly a truncated/garbled response) or a wildly oversized
	one (most plausibly the model echoing injected content back instead of reasoning about the
	job). match_score itself is already clamped to 0-100 by parse_match_response() before this
	runs, so there's nothing further to validate there.
	"""
	if not reasoning.strip():
		raise GuardrailBlockedError(
			guardrail="empty_reasoning",
			category="output_validation",
			job_id=job_id,
			reason=f"job_id={job_id}: model returned an empty reasoning field for match_score={match_score}",
		)
	if len(reasoning) > GUARDRAIL_MAX_REASONING_CHARS:
		raise GuardrailBlockedError(
			guardrail="oversized_reasoning",
			category="output_validation",
			job_id=job_id,
			reason=(
				f"job_id={job_id}: reasoning field is {len(reasoning)} chars, exceeding the "
				f"{GUARDRAIL_MAX_REASONING_CHARS}-char sanity limit"
			),
		)
