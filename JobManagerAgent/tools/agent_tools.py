from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from crawler import CrawlError, NotFoundCrawlError, fetch_job_detail

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
	model_name: str,
) -> tuple[Any, Any, dict[str, Any]]:
	"""Build the 2 LLM-facing tools for one agent cycle, bound to `engine`, a candidate ordering,
	and a batch size the agent doesn't get to choose (mode/order/limit stay under deterministic
	control, same as the non-agentic cycle -- only per-job scoring judgment is the LLM's job).

	Each tool call opens its own short-lived Session rather than sharing one across calls:
	LangGraph's ToolNode always dispatches tool execution through a thread pool (even for a
	single call), so a Session created up front and captured by closure would be handed to a
	worker thread other than the one it was created on -- an immediate crash on SQLite and a
	real thread-safety violation on Postgres. A fresh Session per call sidesteps this regardless
	of which thread runs it.

	Returns `(get_jobs_tool, record_result_tool, stats)`; `stats` is mutated by the tools as
	they run so the caller can compute cycle-level metrics without re-parsing the agent's
	message history afterward.
	"""
	stats: dict[str, Any] = {
		"candidate_count": 0,
		"evaluated_count": 0,
		"matched_count": 0,
		"not_found_jobs": [],
		"crawl_failed_job_ids": [],
	}

	@tool
	def get_jobs_to_process() -> list[dict[str, Any]]:
		"""Fetch the next batch of jobs that have not yet been evaluated. Each item includes the
		full job description, required skills, experience level, salary/equity range, and other
		details crawled from the posting -- everything needed to judge fit against the
		candidate's resume in the system prompt. Jobs whose posting page is gone (404) are
		automatically recorded as non-matches and are not included in the result; you don't need
		to do anything about those. Call this once at the start to get your work for this cycle."""
		with Session(engine) as session:
			candidates = db_get_jobs_to_process(session, limit=limit, order=order)
			stats["candidate_count"] = len(candidates)

			jobs: list[dict[str, Any]] = []
			for candidate in candidates:
				if not candidate.job_url:
					stats["crawl_failed_job_ids"].append(candidate.job_id)
					continue
				try:
					detail = fetch_job_detail(candidate.job_url)
				except NotFoundCrawlError as error:
					db_record_job_result(
						session,
						JobResult(
							job_id=candidate.job_id,
							match_score=0,
							is_match=False,
							reasoning=f"not_found_404 job_url={candidate.job_url}; {error}",
							prompt_name=prompt_name,
							prompt_version=prompt_version,
							model_name=model_name,
						),
					)
					stats["not_found_jobs"].append({"job_id": candidate.job_id, "job_url": candidate.job_url})
					continue
				except CrawlError:
					stats["crawl_failed_job_ids"].append(candidate.job_id)
					continue

				jobs.append(
					{
						"job_id": candidate.job_id,
						"job_role": candidate.job_role,
						"company_name": candidate.company_name,
						**detail,
					}
				)
			return jobs

	@tool
	def record_job_result(job_id: int, match_score: int, reasoning: str) -> str:
		"""Record your evaluation of one job against the resume. `match_score` is 0-100;
		`reasoning` is a short explanation of the score. Call this exactly once per job returned
		by get_jobs_to_process, after you've assessed it -- do not call it more than once for the
		same job_id."""
		is_match = match_score >= threshold
		with Session(engine) as session:
			written = db_record_job_result(
				session,
				JobResult(
					job_id=job_id,
					match_score=match_score,
					is_match=is_match,
					reasoning=reasoning,
					prompt_name=prompt_name,
					prompt_version=prompt_version,
					model_name=model_name,
				),
			)
		if written:
			stats["evaluated_count"] += 1
			if is_match:
				stats["matched_count"] += 1
			return f"recorded job_id={job_id} match_score={match_score} is_match={is_match}"
		return f"job_id={job_id} was already recorded (no-op)"

	return get_jobs_to_process, record_job_result, stats
