from __future__ import annotations

import logging
import time
from typing import Any

from guardrails.checks import check_output
from guardrails.errors import GuardrailBlockedError
from guardrails.injection import scan_job_for_injection
from utils.env_utils import load_env_value

from . import gemini_provider
from .base import (
	CRITERIA_KEYS,
	JobScore,
	MatchResponseError,
	RateLimitError,
	TokenUsage,
	TransientProviderError,
	compute_match_result,
	parse_criteria_response,
	parse_match_response,
	render_prompt,
)


__all__ = [
	"CRITERIA_KEYS",
	"GuardrailBlockedError",
	"JobScore",
	"MatchResponseError",
	"RateLimitError",
	"TokenUsage",
	"TransientProviderError",
	"build_client",
	"call_scoring_model",
	"load_model_name",
	"load_provider_name",
	"parse_criteria_response",
	"parse_match_response",
	"render_prompt",
	"score_job",
	"score_jobs_batch",
]

_ONLY_PROVIDER = "gemini"

_TRANSIENT_MAX_RETRIES = 3
_TRANSIENT_BASE_DELAY_SECONDS = 2.0

# A RateLimitError reaching here should be rare if the caller's own RPM budget (rate_limiter.py)
# is working -- it most often means something outside this process (e.g. another application on
# the same API key) consumed quota within the same window. Worth a couple of short retries with
# backoff before giving up, same reasoning as the TransientProviderError retry above but on a
# longer/explicit delay (the provider's own retry_after when it gives one) rather than fast
# exponential backoff, since a quota window reopening takes longer than a transient glitch
# clearing.
_RATE_LIMIT_MAX_RETRIES = 2
_RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 15.0

LOGGER = logging.getLogger(__name__)


def load_provider_name() -> str:
	name = load_env_value("LLM_PROVIDER", _ONLY_PROVIDER).strip().lower()
	if name and name != _ONLY_PROVIDER:
		raise ValueError(f"Unsupported LLM_PROVIDER {name!r}; only {_ONLY_PROVIDER!r} is supported")
	return _ONLY_PROVIDER


def _provider_module(provider: str | None) -> Any:
	resolved = (provider or load_provider_name()).strip().lower()
	if resolved != _ONLY_PROVIDER:
		raise ValueError(f"Unsupported provider {resolved!r}; only {_ONLY_PROVIDER!r} is supported")
	return gemini_provider


def load_model_name(provider: str | None = None) -> str:
	return _provider_module(provider).load_model()


def build_client(provider: str | None = None) -> Any:
	return _provider_module(provider).build_client()


def call_scoring_model(
	client: Any, *, model: str, prompt: str, provider: str | None = None, bucket: str = "live"
) -> tuple[str, TokenUsage]:
	"""Single LLM scoring call, with retries for the two recoverable failure modes a provider
	call can hit: a transient server-side hiccup (fast exponential backoff) and a rate limit
	(longer backoff, informed by the provider's retry_after when given). Both retry loops run
	here so every caller -- the live/backfill cycle, the ReAct agent's evaluate_match tool, and
	the offline eval harness -- gets the same resilience without redefining it.

	Returns the model's raw response text, unparsed -- score_job()/score_jobs_batch() apply
	whichever parser matches the active prompt's schema_mode (legacy vs rubric criteria), so
	parsing doesn't happen here.

	`bucket` ("live" or "backfill") is threaded straight through to the provider module's
	call_model, which is the actual enforcement point for RPM limiting (see
	gemini_provider.py:_generate_content) -- this function does not acquire an RPM slot itself,
	so a caller can't accidentally bypass the reserved-bucket accounting by calling this instead
	of going through the provider.

	Token usage is only available for the call that actually succeeds -- a retried attempt that
	raised TransientProviderError/RateLimitError never got far enough to report usage, so those
	tokens (if the provider billed any before erroring) aren't reflected here.
	"""
	module = _provider_module(provider)

	transient_attempt = 0
	rate_limit_attempt = 0
	while True:
		try:
			text, usage = module.call_model(client, model=model, prompt=prompt, bucket=bucket)
			return text, usage
		except TransientProviderError:
			transient_attempt += 1
			if transient_attempt > _TRANSIENT_MAX_RETRIES:
				raise
			delay = _TRANSIENT_BASE_DELAY_SECONDS * (2 ** (transient_attempt - 1))
			LOGGER.info("Transient provider error, retrying in %.1fs (attempt %d)", delay, transient_attempt)
			time.sleep(delay)
		except RateLimitError as error:
			rate_limit_attempt += 1
			if rate_limit_attempt > _RATE_LIMIT_MAX_RETRIES:
				raise
			delay = error.retry_after or _RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
			LOGGER.info("Rate limited, retrying in %.1fs (attempt %d)", delay, rate_limit_attempt)
			time.sleep(delay)


def score_job(
	*,
	client: Any,
	model: str,
	provider: str | None = None,
	loaded_prompt: Any,
	resume: str,
	job: dict[str, Any],
	threshold: int,
	job_id: int | None = None,
	bucket: str = "live",
) -> JobScore:
	"""The single definition of 'evaluate one job against the resume': screens the job posting for
	prompt-injection attempts, renders the active prompt template, scores it via
	call_scoring_model (which already retries transient/rate-limit failures), validates the
	response, and applies the match threshold. Used identically by the ReAct agent's
	evaluate_match tool (tools/agent_tools.py) and the offline eval harness
	(evals/run_offline_eval.py) -- there is exactly one place "is this a match" gets decided
	(and one place its guardrails are enforced), so callers can never quietly drift apart.

	`loaded_prompt` is an integrations.mlflow.LoadedPrompt (an MLflow PromptVersion plus its
	schema_mode). schema_mode="legacy" (v1-v3) keeps the original behavior: the model decides
	match_score/reasoning directly. schema_mode="single" (v4) instead asks the model for raw
	per-criterion scores only and derives match_score/reasoning deterministically via
	compute_match_result -- see llm_providers/base.py. schema_mode="batch" is never valid here;
	batch-shaped prompts are only ever scored through score_jobs_batch.

	`bucket` ("live", "backfill", or "eval" -- see utils/config.py's x+y+z+w RPM budget model)
	selects which independent RPM counter this call draws from; defaults to "live" since that's
	every real caller except the offline eval harness, which passes bucket="eval" explicitly.

	Raises GuardrailBlockedError if the job content looks like a prompt-injection attempt or the
	model's response fails output validation -- both checks run here rather than in each caller so
	neither guardrail can be skipped by a caller that forgets to apply it. `job_id` is optional
	(the offline eval harness scores synthetic cases with no real job_id) and only used to attribute
	a raised GuardrailBlockedError to a specific job.
	"""
	schema_mode = getattr(loaded_prompt, "schema_mode", "legacy")
	prompt_version_obj = getattr(loaded_prompt, "version", loaded_prompt)
	if schema_mode == "batch":
		raise ValueError("score_job() scores one job per call; a schema_mode='batch' prompt must use score_jobs_batch()")

	scan_job_for_injection(job_id=job_id, job=job)
	prompt = render_prompt(prompt_version_obj, resume=resume, jobs=[(job_id or 0, job)], schema_mode=schema_mode)
	text, usage = call_scoring_model(client, model=model, prompt=prompt, provider=provider, bucket=bucket)

	score_breakdown: dict[str, dict[str, Any]] | None = None
	if schema_mode == "legacy":
		parsed = parse_match_response(text)
		match_score, reasoning = parsed["match_score"], parsed["reasoning"]
	else:
		items = parse_criteria_response(text)
		if not items:
			raise MatchResponseError("Model response for single-job scoring contained no items")
		score_breakdown = items[0]["criteria"]
		match_score, reasoning = compute_match_result(score_breakdown)

	check_output(job_id=job_id, match_score=match_score, reasoning=reasoning)
	return JobScore(
		match_score=match_score,
		reasoning=reasoning,
		is_match=match_score >= threshold,
		token_usage=usage,
		score_breakdown=score_breakdown,
	)


def score_jobs_batch(
	*,
	client: Any,
	model: str,
	provider: str | None = None,
	loaded_prompt: Any,
	resume: str,
	jobs: list[tuple[int, dict[str, Any]]],
	threshold: int,
	bucket: str = "backfill",
) -> dict[int, JobScore]:
	"""Scores multiple jobs against the resume in a single LLM call, for schema_mode="batch"
	prompts (job_match_v5.txt) only -- this is what backfill/processes/rescore_with_prompt.py
	uses to cut call volume when re-scoring a large backlog under a new prompt, as opposed to
	score_job()'s one-call-per-job live path.

	Each job is screened for prompt-injection independently first; a flagged job is excluded
	from the batch (and absent from the returned dict) rather than failing every other job in
	the batch over one bad posting -- the caller is expected to record/report that exclusion
	itself (backfill/engine.py counts it separately from a successful score).

	One evaluate_match call scores every surviving job at once; each item in the parsed response
	array gets the same deterministic compute_match_result + output guardrail treatment score_job
	applies to a single job. Returns {job_id: JobScore}, keyed by whatever job_id the model
	echoed back -- a job_id present in `jobs` but missing from the model's response (or that fails
	guardrail validation) is simply absent from the result; the caller decides how to handle that
	(retry later, leave unscored) rather than this function guessing.

	`bucket` defaults to "backfill" (the real production caller, rescore_with_prompt.py) but is
	overridable -- the offline eval harness's --batch-size path (evals/run_offline_eval.py) passes
	bucket="eval" so exercising the batch-scoring code path against the golden dataset draws from
	its own reserved RPM counter rather than the real backfill process's.
	"""
	schema_mode = getattr(loaded_prompt, "schema_mode", "legacy")
	prompt_version_obj = getattr(loaded_prompt, "version", loaded_prompt)
	if schema_mode != "batch":
		raise ValueError(f"score_jobs_batch() requires a schema_mode='batch' prompt, got {schema_mode!r}")

	screened_jobs: list[tuple[int, dict[str, Any]]] = []
	for job_id, job in jobs:
		try:
			scan_job_for_injection(job_id=job_id, job=job)
		except GuardrailBlockedError as error:
			LOGGER.warning("job_id=%s excluded from batch: %s", job_id, error)
			continue
		screened_jobs.append((job_id, job))

	if not screened_jobs:
		return {}

	prompt = render_prompt(prompt_version_obj, resume=resume, jobs=screened_jobs, schema_mode=schema_mode)
	batch_job_ids = [job_id for job_id, _ in screened_jobs]
	# Logged unconditionally (not only on failure) so every job item's exact request/response is
	# always available for debugging -- e.g. a MatchResponseError from parse_criteria_response
	# below still has its triggering prompt/response on record even though the exception itself
	# only carries the parser's error text.
	LOGGER.info("score_jobs_batch request bucket=%s job_ids=%s prompt=%s", bucket, batch_job_ids, prompt)
	# The one call this whole batch makes draws from `bucket`'s reserved RPM counter (see
	# gemini_provider.py:_generate_content), never the "live" one score_job() uses -- this, not a
	# caller-side acquire() before calling this function, is what actually keeps a large backfill
	# run from crowding out live scoring's share of the model's real quota.
	text, usage = call_scoring_model(client, model=model, prompt=prompt, provider=provider, bucket=bucket)
	LOGGER.info("score_jobs_batch response bucket=%s job_ids=%s response=%s", bucket, batch_job_ids, text)
	items = parse_criteria_response(text)

	# Token usage is billed once for the whole batch call; attributing the full usage to every
	# job in the batch would multiply-count it if a caller sums usage across jobs, so each job's
	# JobScore instead carries an even split -- good enough for cost accounting without pretending
	# per-job token isolation the underlying call never had.
	per_job_usage = TokenUsage(
		prompt_tokens=usage.prompt_tokens // len(screened_jobs),
		completion_tokens=usage.completion_tokens // len(screened_jobs),
		total_tokens=usage.total_tokens // len(screened_jobs),
	)

	results: dict[int, JobScore] = {}
	screened_job_ids = {job_id for job_id, _ in screened_jobs}
	for item in items:
		job_id = item["job_id"]
		if job_id not in screened_job_ids:
			LOGGER.warning("Model returned unexpected job_id=%s not in this batch; ignoring", job_id)
			continue
		criteria = item["criteria"]
		match_score, reasoning = compute_match_result(criteria)
		try:
			check_output(job_id=job_id, match_score=match_score, reasoning=reasoning)
		except GuardrailBlockedError as error:
			LOGGER.warning("job_id=%s excluded from batch results: %s", job_id, error)
			continue
		results[job_id] = JobScore(
			match_score=match_score,
			reasoning=reasoning,
			is_match=match_score >= threshold,
			token_usage=per_job_usage,
			score_breakdown=criteria,
		)
	return results
