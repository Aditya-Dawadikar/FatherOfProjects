from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import mlflow
from sqlalchemy import func, select
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
from shared.job_match_data import JobMatch, unevaluated_job_ids_stmt
from stream_events import RedisStreamPublisher, publish_event


LOGGER = get_agent_logger(__name__)
RESUME_FILE = Path(__file__).with_name("resume.md")


def load_resume() -> str:
	if not RESUME_FILE.exists():
		raise FileNotFoundError(f"{RESUME_FILE} not found; fill in your resume/skills before running the agent")
	return RESUME_FILE.read_text(encoding="utf-8")


def load_match_threshold() -> int:
	return int(load_env_value("MATCH_THRESHOLD", "70"))


def load_max_jobs_per_cycle() -> int:
	return int(load_env_value("MAX_JOBS_PER_CYCLE", "25"))


def load_request_delay_seconds() -> float:
	# Paces calls between jobs so a cycle doesn't burst the active provider's per-minute limit.
	# Whatever provider is active (see llm_providers), the real constraint in practice tends to
	# be a daily token quota rather than this per-minute pacing -- see README's "LLM provider"
	# section for how to check that.
	return float(load_env_value("LLM_REQUEST_DELAY_SECONDS", "20"))


def run_matching_cycle(publisher: RedisStreamPublisher | None = None, *, cycle_id: str | None = None) -> dict[str, Any]:
	cycle_id = cycle_id or new_id()
	log = LOGGER.bind(cycle_id=cycle_id)

	engine = create_db_engine(load_database_url())
	Base.metadata.create_all(engine)

	resume_text = load_resume()
	prompt_version_obj = get_active_prompt()
	prompt_version = str(prompt_version_obj.version)
	provider = load_provider_name()
	llm_client = build_client(provider)
	llm_model = load_model_name(provider)
	threshold = load_match_threshold()
	max_jobs = load_max_jobs_per_cycle()
	request_delay = load_request_delay_seconds()

	evaluated_count = 0
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
			attributes={"cycle_id": cycle_id, "llm_provider": provider, "llm_model": llm_model},
			run_id=run_id,
		) as cycle_span:
			cycle_span.set_inputs(
				{
					"cycle_id": cycle_id,
					"experiment_name": experiment_name,
					"prompt_name": PROMPT_NAME,
					"prompt_version": prompt_version,
					"match_threshold": threshold,
					"max_jobs_per_cycle": max_jobs,
				}
			)
			mlflow.set_tags({"cycle_id": cycle_id, "prompt_name": PROMPT_NAME, "llm_provider": provider})
			mlflow.log_params(
				{
					"prompt_version": prompt_version,
					"llm_provider": provider,
					"llm_model": llm_model,
					"match_threshold": threshold,
					"max_jobs_per_cycle": max_jobs,
					"llm_request_delay_seconds": request_delay,
				}
			)

			with Session(engine) as session:
				candidates = session.execute(unevaluated_job_ids_stmt(max_jobs)).all()
				log.action("candidates_found", candidate_count=len(candidates), max_jobs=max_jobs)

				for index, (job_id, job_url, job_role, company_name) in enumerate(candidates):
					job_log = log.bind(job_id=job_id)

					if index > 0 and request_delay > 0:
						job_log.sleeping(
							request_delay,
							reason="llm_rate_limit_pacing",
							position=f"{index + 1}/{len(candidates)}",
						)
						time.sleep(request_delay)

					try:
						with mlflow.start_span(
							name="evaluate_job",
							span_type="TASK",
							attributes={
								"job_id": str(job_id),
								"job_role": job_role,
								"company_name": company_name,
							},
						) as job_span:
							job_span.set_inputs({"job_url": job_url, "job_role": job_role, "company_name": company_name})
							_evaluate_one_job(
								session=session,
								job_id=job_id,
								job_url=job_url,
								job_role=job_role,
								company_name=company_name,
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
						# Commit immediately so a job that succeeds is never re-evaluated (and
						# never re-billed against the provider's quota) even if a later job in this
						# same cycle fails or hits a rate limit.
						session.commit()
						evaluated_count += 1
					except RateLimitError as error:
						job_log.action(
							"cycle_stopped_rate_limited",
							evaluated_count=evaluated_count,
							retry_after=error.retry_after,
						)
						rate_limited = True
						break
					except NotFoundCrawlError as error:
						session.rollback()
						not_found_count += 1
						not_found_jobs.append(
							{
								"job_id": job_id,
								"job_url": job_url,
								"job_role": job_role,
								"company_name": company_name,
								"reason": str(error),
							}
						)
						_record_unavailable_job(
							session=session,
							job_id=job_id,
							prompt_version=prompt_version,
							llm_model=llm_model,
							job_url=job_url,
							reason=str(error),
						)
						session.commit()
						evaluated_count += 1
						job_log.action("job_removed_or_missing", job_url=job_url, reason=str(error))
						publish_event(
							publisher,
							"matching_job_url_not_found",
							cycle_id=cycle_id,
							job_id=job_id,
							job_url=job_url,
							job_role=job_role,
							company_name=company_name,
							reason=str(error),
						)
						continue
					except (CrawlError, MatchResponseError, TransientProviderError) as error:
						session.rollback()
						failed_count += 1
						job_log.action("job_skipped", error=str(error))
						continue

				candidate_job_ids = [row[0] for row in candidates]
				matched_count = session.scalar(
					select(func.count())
					.select_from(JobMatch)
					.where(JobMatch.job_id.in_(candidate_job_ids), JobMatch.is_match.is_(True))
				) or 0

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
	publish_event(publisher, "matching_cycle_completed", cycle_id=cycle_id, **result)
	return result


def _evaluate_one_job(
	*,
	session: Session,
	job_id: int,
	job_url: str | None,
	job_role: str,
	company_name: str,
	resume_text: str,
	prompt_version_obj: Any,
	prompt_version: str,
	llm_client: Any,
	llm_model: str,
	provider: str,
	threshold: int,
	log: AgentLogger,
	metric_step: int,
) -> None:
	if not job_url:
		raise CrawlError(f"job_id={job_id} has no job_url to crawl")

	log.action("crawl_start", job_url=job_url, job_role=job_role, company_name=company_name)
	job_detail = fetch_job_detail(job_url)
	job_detail["company_name"] = company_name

	log.action("llm_call_start", provider=provider, model=llm_model, prompt_version=prompt_version)
	prompt = render_prompt(prompt_version_obj, resume=resume_text, job=job_detail)
	result = evaluate_match(llm_client, model=llm_model, prompt=prompt, provider=provider)

	is_match = result["match_score"] >= threshold
	session.add(
		JobMatch(
			job_id=job_id,
			match_score=result["match_score"],
			is_match=is_match,
			reasoning=result["reasoning"],
			prompt_name=PROMPT_NAME,
			prompt_version=prompt_version,
			model_name=llm_model,
		)
	)
	mlflow.log_metrics(
		{"match_score": result["match_score"], "is_match": int(is_match)},
		step=metric_step,
	)
	log.action(
		"match_recorded",
		job_role=job_role,
		match_score=result["match_score"],
		is_match=is_match,
	)


def _record_unavailable_job(
	*,
	session: Session,
	job_id: int,
	prompt_version: str,
	llm_model: str,
	job_url: str | None,
	reason: str,
) -> None:
	"""Persist a non-match marker for jobs with permanently unavailable detail pages."""
	verification_reason = f"not_found_404 job_url={job_url or 'unknown'}; {reason}"
	session.add(
		JobMatch(
			job_id=job_id,
			match_score=0,
			is_match=False,
			reasoning=verification_reason,
			prompt_name=PROMPT_NAME,
			prompt_version=prompt_version,
			model_name=llm_model,
		)
	)
