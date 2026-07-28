from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JobScore:
	"""Result of scoring one job against a resume: what score_job() (see llm_providers/__init__.py)
	returns, and the one shape every caller -- the live/backfill cycle, the ReAct agent's
	evaluate_match tool, and the offline eval harness -- works with."""

	match_score: int
	reasoning: str
	is_match: bool


class MatchResponseError(RuntimeError):
	pass


class RateLimitError(RuntimeError):
	"""Provider-agnostic rate-limit signal. Every provider module catches its own SDK's
	rate-limit exception and re-raises this instead, so react_agent.py/run_offline_eval.py never
	need a per-provider except clause."""

	def __init__(self, message: str, *, retry_after: float | None = None) -> None:
		super().__init__(message)
		self.retry_after = retry_after


class TransientProviderError(RuntimeError):
	"""Provider-agnostic signal for a retryable server-side hiccup (5xx / overloaded / timed
	out / connection dropped) as opposed to RateLimitError (a quota that won't clear by
	retrying seconds later) or MatchResponseError (a response that will never parse no matter
	how many times you ask). evaluate_match() retries these with backoff before giving up."""


def _text_or_blank(value: Any) -> str:
	return "" if value is None else str(value)


def render_prompt(prompt_version: Any, *, resume: str, job: dict[str, Any]) -> str:
	skills = job.get("skills") or []
	return prompt_version.format(
		resume=resume,
		job_title=job.get("title") or "",
		company_name=job.get("company_name") or "",
		location=job.get("location") or "",
		job_type=job.get("job_type") or "",
		min_experience=_text_or_blank(job.get("min_experience")),
		salary_range=job.get("salary_range") or "",
		equity_range=job.get("equity_range") or "",
		sponsors_visa=_text_or_blank(job.get("sponsors_visa")),
		skills=", ".join(skills) if skills else "",
		description_text=job.get("description_text") or "",
		interview_process_text=job.get("interview_process_text") or "",
	)


def _extract_json_object(text: str) -> dict[str, Any]:
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		pass

	match = re.search(r"\{.*\}", text, re.DOTALL)
	if match is None:
		raise MatchResponseError(f"Model response did not contain a JSON object: {text[:200]!r}")

	try:
		return json.loads(match.group(0))
	except json.JSONDecodeError as error:
		raise MatchResponseError(f"Model response JSON could not be parsed: {error}") from error


def parse_match_response(text: str) -> dict[str, Any]:
	parsed = _extract_json_object(text)

	score = parsed.get("match_score")
	if not isinstance(score, (int, float)):
		raise MatchResponseError(f"Model response missing numeric match_score: {parsed!r}")
	clamped_score = max(0, min(100, int(round(score))))

	reasoning = str(parsed.get("reasoning") or "").strip()

	return {"match_score": clamped_score, "reasoning": reasoning}
