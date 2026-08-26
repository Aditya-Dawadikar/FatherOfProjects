from __future__ import annotations

from typing import Any

import mlflow
from langchain_core.tools import tool
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from guardrails.errors import GuardrailBlockedError
from llm_providers import JobScore, MatchResponseError, RateLimitError, TransientProviderError, score_job
from services import CrawlError, NotFoundCrawlError, fetch_job_detail_for_source

from .db_tools import JobResult, Order
from .db_tools import get_jobs_to_process as db_get_jobs_to_process
from .db_tools import record_job_result as db_record_job_result


def build_agent_tools(
	*,
	engine: Engine,
	order: Order,
	limit: int,
	threshold: int,
	prompt_name: str,
	prompt_version: str,
	prompt_version_obj: Any,
	resume_text: str,
	llm_client: Any,
	model_name: str,
	provider: str,
) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
	"""Build the 4 LLM-facing tools for one agent cycle, bound to `engine`, a candidate ordering,
	and a batch size the agent doesn't get to choose (mode/order/limit are fixed by the caller --
	the LLM's job is deciding *which* job to work on next and *when* to crawl/evaluate/record it,
	not reinventing scoring judgment or DB access).

	evaluate_match wraps llm_providers.score_job -- the single scoring definition also used by
	evals/run_offline_eval.py -- instead of letting the ReAct model score freeform. That means a
	cycle's `prompt_version` metadata is actually true (the real MLflow-registered prompt template
	did the scoring), and it inherits gemini_provider.py's full safety net (RPM limiter,
	cooldown+fallback, the truncation fix) rather than only the subset build_llm() wires into the
	ReAct model itself.

	Each tool call opens its own short-lived Session rather than sharing one across calls:
	LangGraph's ToolNode always dispatches tool execution through a thread pool (even for a
	single call), so a Session created up front and captured by closure would be handed to a
	worker thread other than the one it was created on -- an immediate crash on SQLite and a
	real thread-safety violation on Postgres. A fresh Session per call sidesteps this regardless
	of which thread runs it.

	Returns `(get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool, stats)`;
	`stats` is mutated by the tools as they run so the caller can compute cycle-level metrics
	without re-parsing the agent's message history afterward.
	"""
	stats: dict[str, Any] = {
		"candidate_count": 0,
		"evaluated_count": 0,
		"matched_count": 0,
		"not_found_jobs": [],
		"crawl_failed_job_ids": [],
		"evaluate_failed_job_ids": [],
	}
	# job_id -> (source, source_job_id, job_url), populated by get_jobs_to_process and consulted
	# by crawl_job -- keeps job_url/source out of the LLM's hands entirely (it only ever deals in
	# job_id), so there's no way for a mistyped/hallucinated URL to reach the crawler, and lets
	# crawl_job dispatch to the right per-source fetcher (services/crawler.py).
	job_urls: dict[int, tuple[str, str, str | None]] = {}
	# job_id -> crawled detail, populated by crawl_job and consulted by evaluate_match -- the LLM
	# never has to echo the posting text back through tool arguments to get it scored.
	job_details: dict[int, dict[str, Any]] = {}
	# job_id -> JobScore, populated by evaluate_match and consulted by record_job_result -- the
	# LLM never retypes a score/reasoning/is_match it already received, so there is no
	# transcription path for a recorded result to drift from what score_job actually computed.
	job_scores: dict[int, JobScore] = {}

	def _trace_tool_call(tool_name: str, tool_args: dict[str, Any], func: Any) -> Any:
		with mlflow.start_span(
			name=f"tool:{tool_name}",
			span_type="TOOL",
			attributes={"tool_name": tool_name, "tool_args": str(tool_args)},
		) as span:
			span.set_inputs({"args": tool_args})
			try:
				result = func()
			except Exception as error:
				span.set_outputs({"error": str(error)})
				raise
			span.set_outputs({"result": result})
			return result

	@tool
	def get_jobs_to_process() -> list[dict[str, Any]]:
		"""Fetch the next batch of jobs that have not yet been evaluated. Each item has job_id,
		job_role, and company_name only -- call crawl_job(job_id) next for each one to get the
		full posting detail. Call this once at the start to get your work for this cycle; do not
		call it again afterward."""
		return _trace_tool_call(
			"get_jobs_to_process",
			{},
			lambda: _get_jobs_to_process_impl(),
		)

	def _get_jobs_to_process_impl() -> list[dict[str, Any]]:
		with Session(engine) as session:
			candidates = db_get_jobs_to_process(session, limit=limit, order=order)
		stats["candidate_count"] = len(candidates)

		jobs: list[dict[str, Any]] = []
		for candidate in candidates:
			job_urls[candidate.job_id] = (candidate.source, candidate.source_job_id, candidate.job_url)
			jobs.append(
				{
					"job_id": candidate.job_id,
					"job_role": candidate.job_role,
					"company_name": candidate.company_name,
				}
			)
		return jobs

	@tool
	def crawl_job(job_id: int) -> dict[str, Any]:
		"""Fetch the full posting detail for a job_id returned by get_jobs_to_process: full job
		description, required skills, experience level, salary/equity range, and other fields.
		Call this once per job_id, then call evaluate_match(job_id) next.

		If the result contains an "error" key, do not call evaluate_match for that job_id --
		either the posting is gone (404, already automatically recorded as a non-match) or it
		could not be fetched at all; just move on to the next job."""
		return _trace_tool_call(
			"crawl_job",
			{"job_id": job_id},
			lambda: _crawl_job_impl(job_id),
		)

	def _crawl_job_impl(job_id: int) -> dict[str, Any]:
		entry = job_urls.get(job_id)
		if job_id not in job_urls:
			raise GuardrailBlockedError(
				guardrail="unknown_job_id",
				category="tool_usage",
				job_id=job_id,
				reason=f"unknown job_id={job_id}; call get_jobs_to_process first",
			)
		source, source_job_id, job_url = entry
		if not job_url:
			stats["crawl_failed_job_ids"].append(job_id)
			return {"error": f"job_id={job_id} has no URL on file; skip it"}

		try:
			detail = fetch_job_detail_for_source(source, job_url, source_job_id)
		except NotFoundCrawlError as error:
			with Session(engine) as session:
				db_record_job_result(
					session,
					JobResult(
						job_listing_id=job_id,
						match_score=0,
						is_match=False,
						reasoning=f"not_found_404 job_url={job_url}; {error}",
						prompt_name=prompt_name,
						prompt_version=prompt_version,
						rubric_version=prompt_version_obj.rubric_version,
						model_name=model_name,
					),
				)
			stats["not_found_jobs"].append({"job_id": job_id, "job_url": job_url})
			return {"error": f"job_id={job_id} posting not found (404); automatically recorded as a non-match"}
		except CrawlError as error:
			stats["crawl_failed_job_ids"].append(job_id)
			return {"error": f"job_id={job_id} could not be crawled: {error}"}

		job_details[job_id] = detail
		return detail

	@tool
	def evaluate_match(job_id: int) -> dict[str, Any]:
		"""Score a job you've already crawled via crawl_job against the candidate's resume.
		This calls score_job() -- the same scoring pipeline the non-agentic matching cycle and
		the offline eval harness use, not your own judgment. Returns {"match_score": 0-100,
		"reasoning": str}. Call this once per successfully crawled job, then call
		record_job_result(job_id) to persist it -- you do not need to pass the score back
		yourself."""
		return _trace_tool_call(
			"evaluate_match",
			{"job_id": job_id},
			lambda: _evaluate_match_impl(job_id),
		)

	def _evaluate_match_impl(job_id: int) -> dict[str, Any]:
		detail = job_details.get(job_id)
		if detail is None:
			raise GuardrailBlockedError(
				guardrail="evaluate_before_crawl",
				category="tool_usage",
				job_id=job_id,
				reason=f"job_id={job_id} has not been crawled yet; call crawl_job first",
			)

		try:
			score = score_job(
				client=llm_client,
				model=model_name,
				provider=provider,
				loaded_prompt=prompt_version_obj,
				resume=resume_text,
				job=detail,
				threshold=threshold,
				job_id=job_id,
			)
		except RateLimitError as error:
			stats["evaluate_failed_job_ids"].append(job_id)
			return {"error": f"rate limited while evaluating job_id={job_id}: {error}"}
		except (MatchResponseError, TransientProviderError) as error:
			stats["evaluate_failed_job_ids"].append(job_id)
			return {"error": f"could not evaluate job_id={job_id}: {error}"}

		job_scores[job_id] = score
		return {"match_score": score.match_score, "reasoning": score.reasoning}

	@tool
	def record_job_result(job_id: int) -> str:
		"""Persist the evaluation for a job you've already scored via evaluate_match. Call this
		once per job, immediately after evaluate_match succeeds for it -- do not call it more
		than once for the same job_id, and never call it for a job_id evaluate_match returned an
		error for."""
		return _trace_tool_call(
			"record_job_result",
			{"job_id": job_id},
			lambda: _record_job_result_impl(job_id),
		)

	def _record_job_result_impl(job_id: int) -> str:
		score = job_scores.get(job_id)
		if score is None:
			raise GuardrailBlockedError(
				guardrail="record_before_evaluate",
				category="tool_usage",
				job_id=job_id,
				reason=f"job_id={job_id} has not been evaluated yet; call evaluate_match first",
			)

		with Session(engine) as session:
			written = db_record_job_result(
				session,
				JobResult(
					job_listing_id=job_id,
					match_score=score.match_score,
					is_match=score.is_match,
					reasoning=score.reasoning,
					prompt_name=prompt_name,
					prompt_version=prompt_version,
					rubric_version=prompt_version_obj.rubric_version,
					model_name=model_name,
					score_breakdown=score.score_breakdown,
				),
			)
		if written:
			stats["evaluated_count"] += 1
			if score.is_match:
				stats["matched_count"] += 1
			return f"recorded job_id={job_id} match_score={score.match_score} is_match={score.is_match}"
		return f"job_id={job_id} was already recorded (no-op)"

	return get_jobs_to_process, crawl_job, evaluate_match, record_job_result, stats
