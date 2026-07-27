from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crawler import CrawlError, fetch_job_detail
from env_utils import load_env_value
from groq_client import MatchResponseError, build_client, evaluate_match, load_groq_model, render_prompt
from prompt_registry import PROMPT_NAME, get_active_prompt
from shared.job_data import Base, create_db_engine, load_database_url
from shared.job_match_data import JobMatch, unevaluated_job_ids_stmt
from stream_events import RedisStreamPublisher, publish_event


LOGGER = logging.getLogger(__name__)
RESUME_FILE = Path(__file__).with_name("resume.md")


def load_resume() -> str:
	if not RESUME_FILE.exists():
		raise FileNotFoundError(f"{RESUME_FILE} not found; fill in your resume/skills before running the agent")
	return RESUME_FILE.read_text(encoding="utf-8")


def load_match_threshold() -> int:
	return int(load_env_value("MATCH_THRESHOLD", "70"))


def load_max_jobs_per_cycle() -> int:
	return int(load_env_value("MAX_JOBS_PER_CYCLE", "25"))


def run_matching_cycle(publisher: RedisStreamPublisher | None = None) -> dict[str, int]:
	engine = create_db_engine(load_database_url())
	Base.metadata.create_all(engine)

	resume_text = load_resume()
	prompt_version_obj = get_active_prompt()
	prompt_version = str(prompt_version_obj.version)
	groq_client = build_client()
	groq_model = load_groq_model()
	threshold = load_match_threshold()
	max_jobs = load_max_jobs_per_cycle()

	evaluated_count = 0
	matched_count = 0
	failed_count = 0

	with Session(engine) as session:
		candidates = session.execute(unevaluated_job_ids_stmt(max_jobs)).all()
		LOGGER.info("Found %s unevaluated job(s) for this cycle", len(candidates))

		for job_id, job_url, job_role, company_name in candidates:
			try:
				evaluated_count += _evaluate_one_job(
					session=session,
					job_id=job_id,
					job_url=job_url,
					job_role=job_role,
					company_name=company_name,
					resume_text=resume_text,
					prompt_version_obj=prompt_version_obj,
					prompt_version=prompt_version,
					groq_client=groq_client,
					groq_model=groq_model,
					threshold=threshold,
				)
			except (CrawlError, MatchResponseError) as error:
				failed_count += 1
				LOGGER.warning("Skipping job_id=%s after error: %s", job_id, error)
				continue

		session.commit()

		candidate_job_ids = [row[0] for row in candidates]
		matched_count = session.scalar(
			select(func.count())
			.select_from(JobMatch)
			.where(JobMatch.job_id.in_(candidate_job_ids), JobMatch.is_match.is_(True))
		) or 0

	result = {
		"candidate_count": len(candidates),
		"evaluated_count": evaluated_count,
		"matched_count": matched_count,
		"failed_count": failed_count,
	}
	LOGGER.info("Matching cycle complete: %s", result)
	publish_event(publisher, "matching_cycle_completed", **result)
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
	groq_client: Any,
	groq_model: str,
	threshold: int,
) -> int:
	if not job_url:
		raise CrawlError(f"job_id={job_id} has no job_url to crawl")

	LOGGER.info("Crawling job_id=%s url=%s", job_id, job_url)
	job_detail = fetch_job_detail(job_url)
	job_detail["company_name"] = company_name

	prompt = render_prompt(prompt_version_obj, resume=resume_text, job=job_detail)
	result = evaluate_match(groq_client, model=groq_model, prompt=prompt)

	is_match = result["match_score"] >= threshold
	session.add(
		JobMatch(
			job_id=job_id,
			match_score=result["match_score"],
			is_match=is_match,
			reasoning=result["reasoning"],
			prompt_name=PROMPT_NAME,
			prompt_version=prompt_version,
			model_name=groq_model,
		)
	)
	LOGGER.info(
		"Evaluated job_id=%s role=%r score=%s is_match=%s",
		job_id,
		job_role,
		result["match_score"],
		is_match,
	)
	return 1
