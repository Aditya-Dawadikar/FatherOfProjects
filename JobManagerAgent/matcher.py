from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

import mlflow
from sqlalchemy.orm import Session

from agent_logger import AgentLogger, get_agent_logger, new_id
from crawler import CrawlError, NotFoundCrawlError, fetch_job_detail
from env_utils import load_env_value
from llm_providers import (
	MatchResponseError,
	RateLimitError,
	TransientProviderError,
	build_client,
	evaluate_match,
	load_model_name,
	load_provider_name,
	render_prompt,
)
from mlflow_utils import ensure_tracking_uri_configured, get_tracking_uri, load_mlflow_experiment_name
from prompt_registry import PROMPT_NAME, get_active_prompt
from shared.job_data import Base, create_db_engine, load_database_url
from stream_events import RedisStreamPublisher, publish_event
from tools import JobCandidate, JobResult, get_jobs_to_process, record_job_result


Mode = Literal["live", "backfill"]

LOGGER = get_agent_logger(__name__)
RESUME_FILE = Path(__file__).with_name("resume.md")

_ORDER_BY_MODE: dict[Mode, str] = {"live": "newest", "backfill": "oldest"}

# The LLM rate limiter (see rate_limiter.py) proactively paces calls under a self-imposed RPM
# budget, so a RateLimitError reaching here should be rare -- it means the shared project quota
# was consumed by something outside this process (e.g. another app on the same API key) within
# the same window. Worth a couple of short retries before giving up on that one job for this
# cycle: it stays unrecorded, so the next cycle (live or backfill) picks it back up for free via
# the same idempotent query, instead of the whole batch being discarded like before.
_RATE_LIMIT_RETRY_ATTEMPTS = 2
_RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 15.0


def load_resume() -> str:
	if not RESUME_FILE.exists():
		raise FileNotFoundError(f"{RESUME_FILE} not found; fill in your resume/skills before running the agent")
	return RESUME_FILE.read_text(encoding="utf-8")


def load_match_threshold() -> int:
	return int(load_env_value("MATCH_THRESHOLD", "70"))


def load_max_jobs_per_cycle() -> int:
	# Kept small on purpose: real throughput is now capped at a few requests/minute by the LLM
	# rate limiter, so a big batch just ties up one cycle for many minutes without checking for
	# new live-trigger events. Smaller batches keep live and backfill work interleaved.
	return int(load_env_value("MAX_JOBS_PER_CYCLE", "5"))


def _empty_result() -> dict[str, Any]:
	return {
		"candidate_count": 0,
		"evaluated_count": 0,
		"matched_count": 0,
		"failed_count": 0,
		"not_found_count": 0,
		"not_found_jobs_sample": [],
		"rate_limited": False,
	}


def run_matching_cycle(
	publisher: RedisStreamPublisher | None = None,
	*,
	cycle_id: str | None = None,
	mode: Mode = "live",
) -> dict[str, Any]:
	cycle_id = cycle_id or new_id()
	log = LOGGER.bind(cycle_id=cycle_id, mode=mode)

	engine = create_db_engine(load_database_url())
	Base.metadata.create_all(engine)

	max_jobs = load_max_jobs_per_cycle()
	order = _ORDER_BY_MODE[mode]

	with Session(engine) as session:
		candidates = get_jobs_to_process(session, limit=max_jobs, order=order)

	if not candidates:
		log.action("no_candidates", mode=mode)
		return _empty_result()

	resume_text = load_resume()
	prompt_version_obj = get_active_prompt()
	prompt_version = str(prompt_version_obj.version)
	provider = load_provider_name()
	llm_client = build_client(provider)
	llm_model = load_model_name(provider)
	threshold = load_match_threshold()

	evaluated_count = 0
	matched_count = 0
	failed_count = 0
	not_found_count = 0
	rate_limited = False
	not_found_jobs: list[dict[str, Any]] = []

	ensure_tracking_uri_configured()
	experiment_name = load_mlflow_experiment_name()
	mlflow.set_experiment(experiment_name)
	log.action("mlflow_target", tracking_uri=get_tracking_uri(), experiment_name=experiment_name)

	with mlflow.start_run(run_name=f"cycle-{cycle_id}"):
		run = mlflow.active_run()
		if run is not None:
			log.action("mlflow_run_started", run_id=run.info.run_id)
		run_id = run.info.run_id if run is not None else None
		with mlflow.start_span(
			name="matching_cycle",
			span_type="WORKFLOW",
			attributes={"cycle_id": cycle_id, "mode": mode, "llm_provider": provider, "llm_model": llm_model},
			run_id=run_id,
		) as cycle_span:
			cycle_span.set_inputs(
				{
					"cycle_id": cycle_id,
					"mode": mode,
					"experiment_name": experiment_name,
					"prompt_name": PROMPT_NAME,
					"prompt_version": prompt_version,
					"match_threshold": threshold,
					"max_jobs_per_cycle": max_jobs,
				}
			)
			mlflow.set_tags({"cycle_id": cycle_id, "mode": mode, "prompt_name": PROMPT_NAME, "llm_provider": provider})
			mlflow.log_params(
				{
					"prompt_version": prompt_version,
					"llm_provider": provider,
					"llm_model": llm_model,
					"match_threshold": threshold,
					"max_jobs_per_cycle": max_jobs,
				}
			)

			log.action("candidates_found", candidate_count=len(candidates), max_jobs=max_jobs)

			with Session(engine) as session:
				for index, candidate in enumerate(candidates):
					job_log = log.bind(job_id=candidate.job_id)

					try:
						with mlflow.start_span(
							name="evaluate_job",
							span_type="TASK",
							attributes={
								"job_id": str(candidate.job_id),
								"job_role": candidate.job_role,
								"company_name": candidate.company_name,
							},
						) as job_span:
							job_span.set_inputs(
								{
									"job_url": candidate.job_url,
									"job_role": candidate.job_role,
									"company_name": candidate.company_name,
								}
							)
							is_match = _evaluate_and_record_one_job(
								session=session,
								candidate=candidate,
								resume_text=resume_text,
								prompt_version_obj=prompt_version_obj,
								prompt_version=prompt_version,
								llm_client=llm_client,
								llm_model=llm_model,
								provider=provider,
								threshold=threshold,
								log=job_log,
								metric_step=index,
							)
							job_span.set_outputs({"status": "ok"})
						evaluated_count += 1
						if is_match:
							matched_count += 1
					except RateLimitError as error:
						rate_limited = True
						job_log.action(
							"job_skipped_rate_limited",
							evaluated_count=evaluated_count,
							retry_after=error.retry_after,
						)
						continue
					except NotFoundCrawlError as error:
						not_found_count += 1
						not_found_jobs.append(
							{
								"job_id": candidate.job_id,
								"job_url": candidate.job_url,
								"job_role": candidate.job_role,
								"company_name": candidate.company_name,
								"reason": str(error),
							}
						)
						_record_unavailable_job(
							session=session,
							candidate=candidate,
							prompt_version=prompt_version,
							llm_model=llm_model,
							reason=str(error),
						)
						evaluated_count += 1
						job_log.action("job_removed_or_missing", job_url=candidate.job_url, reason=str(error))
						publish_event(
							publisher,
							"matching_job_url_not_found",
							cycle_id=cycle_id,
							job_id=candidate.job_id,
							job_url=candidate.job_url,
							job_role=candidate.job_role,
							company_name=candidate.company_name,
							reason=str(error),
						)
						continue
					except (CrawlError, MatchResponseError, TransientProviderError) as error:
						failed_count += 1
						job_log.action("job_skipped", error=str(error))
						continue

			result: dict[str, Any] = {
				"candidate_count": len(candidates),
				"evaluated_count": evaluated_count,
				"matched_count": matched_count,
				"failed_count": failed_count,
				"not_found_count": not_found_count,
				"not_found_jobs_sample": not_found_jobs[:10],
				"rate_limited": rate_limited,
			}
			mlflow.log_metrics(
				{
					"candidate_count": result["candidate_count"],
					"evaluated_count": result["evaluated_count"],
					"matched_count": result["matched_count"],
					"failed_count": result["failed_count"],
					"not_found_count": result["not_found_count"],
					"rate_limited": int(result["rate_limited"]),
				}
			)
			if not_found_count > 0:
				log.action(
					"not_found_urls_summary",
					not_found_count=not_found_count,
					not_found_jobs_sample=result["not_found_jobs_sample"],
				)
			cycle_span.set_outputs(result)
			log.action("mlflow_trace_ready", trace_id=cycle_span.trace_id)

		# Traces are exported asynchronously; force a flush in case the process exits soon.
		mlflow.flush_trace_async_logging(terminate=False)

	log.action("cycle_complete", **result)
	publish_event(publisher, "matching_cycle_completed", cycle_id=cycle_id, mode=mode, **result)
	return result


def _evaluate_and_record_one_job(
	*,
	session: Session,
	candidate: JobCandidate,
	resume_text: str,
	prompt_version_obj: Any,
	prompt_version: str,
	llm_client: Any,
	llm_model: str,
	provider: str,
	threshold: int,
	log: AgentLogger,
	metric_step: int,
) -> bool:
	if not candidate.job_url:
		raise CrawlError(f"job_id={candidate.job_id} has no job_url to crawl")

	log.action(
		"crawl_start", job_url=candidate.job_url, job_role=candidate.job_role, company_name=candidate.company_name
	)
	job_detail = fetch_job_detail(candidate.job_url)
	job_detail["company_name"] = candidate.company_name

	log.action("llm_call_start", provider=provider, model=llm_model, prompt_version=prompt_version)
	prompt = render_prompt(prompt_version_obj, resume=resume_text, job=job_detail)
	result = _evaluate_with_rate_limit_retries(
		llm_client=llm_client, llm_model=llm_model, prompt=prompt, provider=provider, log=log
	)

	is_match = result["match_score"] >= threshold
	# Commit immediately so a job that succeeds is never re-evaluated (and never re-billed
	# against the provider's quota) even if a later job in this same cycle fails.
	written = record_job_result(
		session,
		JobResult(
			job_id=candidate.job_id,
			match_score=result["match_score"],
			is_match=is_match,
			reasoning=result["reasoning"],
			prompt_name=PROMPT_NAME,
			prompt_version=prompt_version,
			model_name=llm_model,
		),
	)
	if not written:
		log.action("match_already_recorded", job_role=candidate.job_role)
	else:
		log.action("match_recorded", job_role=candidate.job_role, match_score=result["match_score"], is_match=is_match)

	mlflow.log_metrics({"match_score": result["match_score"], "is_match": int(is_match)}, step=metric_step)
	return is_match


def _evaluate_with_rate_limit_retries(
	*, llm_client: Any, llm_model: str, prompt: str, provider: str, log: AgentLogger
) -> dict[str, Any]:
	attempt = 0
	while True:
		try:
			return evaluate_match(llm_client, model=llm_model, prompt=prompt, provider=provider)
		except RateLimitError as error:
			attempt += 1
			if attempt > _RATE_LIMIT_RETRY_ATTEMPTS:
				raise
			backoff = error.retry_after or _RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
			log.sleeping(backoff, reason="rate_limit_retry", attempt=attempt)
			time.sleep(backoff)


def _record_unavailable_job(
	*,
	session: Session,
	candidate: JobCandidate,
	prompt_version: str,
	llm_model: str,
	reason: str,
) -> None:
	"""Persist a non-match marker for jobs with permanently unavailable detail pages."""
	verification_reason = f"not_found_404 job_url={candidate.job_url or 'unknown'}; {reason}"
	record_job_result(
		session,
		JobResult(
			job_id=candidate.job_id,
			match_score=0,
			is_match=False,
			reasoning=verification_reason,
			prompt_name=PROMPT_NAME,
			prompt_version=prompt_version,
			model_name=llm_model,
		),
	)
