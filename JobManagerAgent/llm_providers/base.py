from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenUsage:
	"""Token accounting for one LLM call. completion_tokens folds in any "thinking"/reasoning
	tokens the provider bills for (e.g. Gemini's thoughts_token_count) alongside the visible
	output -- both cost money, and no caller needs the split, just the total generation cost
	against what went in as context."""

	prompt_tokens: int
	completion_tokens: int
	total_tokens: int


@dataclass(frozen=True)
class JobScore:
	"""Result of scoring one job against a resume: what score_job()/score_jobs_batch() (see
	llm_providers/__init__.py) return, and the one shape every caller -- the live/backfill
	cycle, the ReAct agent's evaluate_match tool, and the offline eval harness -- works with.

	score_breakdown is the raw per-criterion dict (see compute_match_result) for rubric-based
	prompts (schema_mode "single"/"batch", e.g. job_match_v4/v5); it's None for legacy (v1-v3)
	results, whose match_score/reasoning were decided by the LLM directly rather than
	aggregated deterministically from criteria.
	"""

	match_score: int
	reasoning: str
	is_match: bool
	token_usage: TokenUsage
	score_breakdown: dict[str, dict[str, Any]] | None = None


class MatchResponseError(RuntimeError):
	pass


class RateLimitError(RuntimeError):
	"""Provider-agnostic rate-limit signal. Every provider module catches its own SDK's
	rate-limit exception and re-raises this instead, so react_agent.py/run_offline_eval.py never
	need a per-provider except clause."""

	def __init__(self, message: str, *, retry_after: float | None = None) -> None:
		super().__init__(message)
		self.retry_after = retry_after


class BillingExhaustedError(RuntimeError):
	"""Provider-agnostic signal for a 429 that means "this API key/project is out of prepaid
	credits" (Gemini's RESOURCE_EXHAUSTED-with-a-billing-message, as opposed to an ordinary
	per-minute rate limit -- see gemini_provider.py's _is_billing_exhausted_message). Deliberately
	NOT a RateLimitError subclass: call_scoring_model's retry loop only catches RateLimitError,
	and retrying a billing exhaustion is pointless -- the quota isn't coming back in 15-60
	seconds, only after the operator tops up credits. utils/token_budget.py records this
	persistently (Redis) the moment it's detected, so GET /admin/token-budget can surface it on
	the dashboard even for a caller that doesn't itself handle this exception specially."""


class TransientProviderError(RuntimeError):
	"""Provider-agnostic signal for a retryable server-side hiccup (5xx / overloaded / timed
	out / connection dropped) as opposed to RateLimitError (a quota that won't clear by
	retrying seconds later) or MatchResponseError (a response that will never parse no matter
	how many times you ask). evaluate_match() retries these with backoff before giving up."""


# --- Rubric criteria (schema_mode "single"/"batch", e.g. job_match_v4.txt/v5.txt) --------------
# The LLM only ever returns raw per-criterion scores on this fixed 0-10 scale; the 0-100
# match_score is always derived from these by compute_match_result() below, never by the model.
CRITERIA_KEYS: tuple[str, ...] = (
	"skills_match",
	"experience_fit",
	"location_visa_fit",
	"compensation_fit",
	"role_scope_fit",
)
CRITERION_MIN = 0
CRITERION_MAX = 10
_CRITERIA_MAX_TOTAL = CRITERION_MAX * len(CRITERIA_KEYS)


def _text_or_blank(value: Any) -> str:
	return "" if value is None else str(value)


def _job_fields(job: dict[str, Any]) -> dict[str, str]:
	skills = job.get("skills") or []
	return {
		"job_title": job.get("title") or "",
		"company_name": job.get("company_name") or "",
		"location": job.get("location") or "",
		"job_type": job.get("job_type") or "",
		"min_experience": _text_or_blank(job.get("min_experience")),
		"salary_range": job.get("salary_range") or "",
		"equity_range": job.get("equity_range") or "",
		"sponsors_visa": _text_or_blank(job.get("sponsors_visa")),
		"skills": ", ".join(skills) if skills else "",
		"description_text": job.get("description_text") or "",
		"interview_process_text": job.get("interview_process_text") or "",
	}


# Per-job block used only to build a batch prompt's {{jobs_block}} placeholder (schema_mode
# "batch", e.g. job_match_v5.txt). Deliberately kept in code rather than in the versioned
# prompt file -- it's pure formatting glue repeated N times, not part of the scored rubric, so
# it doesn't need its own MLflow prompt version.
_JOB_BLOCK_TEMPLATE = """--- Job ID: {job_id} ---
Title: {job_title}
Company: {company_name}
Location: {location}
Job type: {job_type}
Minimum experience: {min_experience}
Salary range: {salary_range}
Equity range: {equity_range}
Sponsors visa: {sponsors_visa}
Skills listed: {skills}

Description:
{description_text}

Interview process:
{interview_process_text}
"""


def render_prompt(
	prompt_version: Any,
	*,
	resume: str,
	jobs: list[tuple[int, dict[str, Any]]],
	schema_mode: str = "legacy",
) -> str:
	"""Renders the active prompt template against one resume and 1+ jobs.

	`schema_mode` (read off the prompt's sidecar metadata -- see
	integrations/mlflow/prompt_registry.py) picks the rendering shape:
	- "legacy" (v1-v3, no sidecar file): exactly one job, today's flat placeholders inline in
	  the template, byte-for-byte unchanged from before rubric scoring existed.
	- "single" (v4): exactly one job, same flat placeholders plus {{job_id}}, since v4's JSON
	  output is job_id-tagged.
	- "batch" (v5): N jobs, rendered as a repeated {{jobs_block}} built from
	  _JOB_BLOCK_TEMPLATE above.
	"""
	if schema_mode == "batch":
		blocks = "\n".join(_JOB_BLOCK_TEMPLATE.format(job_id=job_id, **_job_fields(job)) for job_id, job in jobs)
		return prompt_version.format(resume=resume, jobs_block=blocks)

	if len(jobs) != 1:
		raise ValueError(f"schema_mode={schema_mode!r} renders exactly one job at a time, got {len(jobs)}")
	job_id, job = jobs[0]
	fields = _job_fields(job)
	if schema_mode == "single":
		return prompt_version.format(resume=resume, job_id=job_id, **fields)
	return prompt_version.format(resume=resume, **fields)


def _parse_array_partial(text: str, start: int) -> list[Any]:
	"""Recovers as many complete top-level elements as possible from a JSON array that was cut
	off mid-generation (e.g. the provider stopped partway through a batch-scoring response,
	leaving the last item -- and the closing ']' -- missing). Parses elements one at a time with
	`raw_decode` and stops at the first one that doesn't parse cleanly, which is almost always
	the truncated trailing element, rather than one bad character anywhere invalidating the
	whole array. `text[start]` must be '['.
	"""
	decoder = json.JSONDecoder()
	whitespace_and_comma = " \t\n\r,"
	idx = start + 1
	items: list[Any] = []
	while True:
		while idx < len(text) and text[idx] in whitespace_and_comma:
			idx += 1
		if idx >= len(text) or text[idx] == "]":
			return items
		try:
			value, idx = decoder.raw_decode(text, idx)
		except json.JSONDecodeError:
			return items
		items.append(value)


def _extract_json_value(text: str) -> Any:
	"""Parses `text` as JSON, tolerating trailing content after a complete value (e.g. a stray
	model note, a repeated echo, or thinking-mode scratch text that leaked into the visible
	response) -- a real risk here since the response is expected to be array/object-shaped and
	near-certain to itself contain '{'/'['/'}'/']' characters. `raw_decode` parses only the
	first complete JSON value starting at `start` and simply ignores whatever follows, instead of
	a greedy bracket-matching regex that spans all the way to the *last* bracket in the text and
	folds any trailing junk into what looks like one (invalid) JSON blob -- that greedy-match
	failure mode is what previously surfaced as opaque `json.JSONDecodeError` "Extra data"
	messages with no indication of what was actually returned.

	Separately, a batch response can be cut off mid-generation -- the array never gets its
	closing ']' because the provider stopped before finishing the last item. That isn't "extra
	data", it's missing data, so raw_decode alone can't recover it: there's no complete value to
	decode starting at `start` at all. `_parse_array_partial` handles that case by salvaging
	whichever leading items did complete, so one truncated trailing item costs only itself
	instead of the whole batch.
	"""
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		pass

	start = next((index for index, char in enumerate(text) if char in "{["), None)
	if start is None:
		raise MatchResponseError(f"Model response did not contain a JSON object/array: {text[:200]!r}")

	try:
		value, _end = json.JSONDecoder().raw_decode(text, start)
		return value
	except json.JSONDecodeError as error:
		if text[start] == "[":
			items = _parse_array_partial(text, start)
			if items:
				LOGGER.warning(
					"Model response array was truncated mid-generation; recovered %d complete item(s) and "
					"discarded the incomplete tail. parse_error=%s",
					len(items),
					error,
				)
				return items
		raise MatchResponseError(
			f"Model response JSON could not be parsed: {error}; full response was: {text!r}"
		) from error


def parse_match_response(text: str) -> dict[str, Any]:
	"""Legacy (schema_mode "legacy", v1-v3) response parsing: the model decides match_score and
	reasoning directly. Untouched by rubric scoring -- see parse_criteria_response for v4/v5.
	"""
	parsed = _extract_json_value(text)
	if not isinstance(parsed, dict):
		raise MatchResponseError(f"Model response was not a JSON object: {parsed!r}")

	score = parsed.get("match_score")
	if not isinstance(score, (int, float)):
		raise MatchResponseError(f"Model response missing numeric match_score: {parsed!r}")
	clamped_score = max(0, min(100, int(round(score))))

	reasoning = str(parsed.get("reasoning") or "").strip()

	return {"match_score": clamped_score, "reasoning": reasoning}


def _validate_criteria(criteria: Any, *, job_id: Any) -> dict[str, dict[str, Any]]:
	if not isinstance(criteria, dict):
		raise MatchResponseError(f"job_id={job_id!r}: 'criteria' must be a JSON object, got {type(criteria).__name__}")

	missing = [key for key in CRITERIA_KEYS if key not in criteria]
	if missing:
		raise MatchResponseError(f"job_id={job_id!r}: criteria response missing required keys {missing}")

	validated: dict[str, dict[str, Any]] = {}
	for key in CRITERIA_KEYS:
		entry = criteria[key]
		if not isinstance(entry, dict) or not isinstance(entry.get("score"), (int, float)):
			raise MatchResponseError(f"job_id={job_id!r}: criteria[{key!r}] missing a numeric 'score'")
		clamped = max(CRITERION_MIN, min(CRITERION_MAX, int(round(entry["score"]))))
		validated[key] = {"score": clamped, "reasoning": str(entry.get("reasoning") or "").strip()}

	return validated


def parse_criteria_response(text: str) -> list[dict[str, Any]]:
	"""Parses a rubric-based (schema_mode "single"/"batch") response -- a single JSON object
	(v4) or a JSON array of objects (v5), normalized to a list either way -- into
	[{"job_id": ..., "criteria": {...}}, ...]. Each criterion score is clamped to
	[CRITERION_MIN, CRITERION_MAX]. The overall match_score is deliberately NOT computed here
	-- see compute_match_result -- this function only validates/normalizes what the model
	actually returned.
	"""
	parsed = _extract_json_value(text)
	items = parsed if isinstance(parsed, list) else [parsed]

	results: list[dict[str, Any]] = []
	for item in items:
		if not isinstance(item, dict) or "job_id" not in item:
			raise MatchResponseError(f"Model response item missing 'job_id': {item!r}")
		results.append({"job_id": item["job_id"], "criteria": _validate_criteria(item.get("criteria"), job_id=item["job_id"])})
	return results


def compute_match_result(criteria: dict[str, dict[str, Any]]) -> tuple[int, str]:
	"""The single deterministic place a 0-100 match_score and its summary reasoning are derived
	from raw per-criterion scores (0-10 each, 5 criteria => 50 max). The LLM only ever supplies
	criteria (see parse_criteria_response); it never decides the aggregate itself, so the
	scoring formula can't drift call-to-call the way an LLM-authored overall score could.
	"""
	total = sum(entry["score"] for entry in criteria.values())
	match_score = max(0, min(100, round(total / _CRITERIA_MAX_TOTAL * 100)))

	ranked = sorted(criteria.items(), key=lambda pair: pair[1]["score"])
	weakest_name, weakest = ranked[0]
	strongest_name, strongest = ranked[-1]
	headline = (
		f"Strongest fit: {strongest_name} ({strongest['score']}/10). "
		f"Weakest fit: {weakest_name} ({weakest['score']}/10)."
	)
	details = "; ".join(
		f"{name} ({entry['score']}/10): {entry['reasoning']}" for name, entry in criteria.items() if entry["reasoning"]
	)
	reasoning = f"{headline} {details}".strip() if details else headline
	return match_score, reasoning
