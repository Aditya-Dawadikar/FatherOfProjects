from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.job_data import JobListing
from shared.job_match_data import JobMatch, reprocess_candidates_stmt
from utils.agent_logger import get_agent_logger


LOGGER = get_agent_logger(__name__)

Order = Literal["newest", "oldest"]


@dataclass(frozen=True)
class JobCandidate:
	job_id: int
	job_url: str | None
	job_role: str
	company_name: str


def get_jobs_to_process(session: Session, *, limit: int, order: Order) -> list[JobCandidate]:
	"""Tool: fetch up to `limit` job_listings rows that have no job_matches row yet.

	`order="newest"` favors freshly scraped jobs (the live-trigger path); `order="oldest"`
	drains the tail of the backlog first so it can never be starved by a steady stream of new
	arrivals (the backfill path). Both orderings query the exact same anti-join, so a job
	picked up by one mode is never re-picked by the other once it has been recorded -- that's
	what makes running this from either mode safe to repeat.
	"""
	order_column = JobListing.updated_at.desc() if order == "newest" else JobListing.updated_at.asc()
	# Idempotency check: a job_id already present in job_matches has already been evaluated (by
	# this cycle or an earlier one) and is silently excluded here rather than re-evaluated -- the
	# log line below is what makes that exclusion visible instead of invisible.
	not_yet_evaluated = JobListing.job_id.notin_(select(JobMatch.job_id))
	stmt = (
		select(JobListing.job_id, JobListing.job_url, JobListing.job_role, JobListing.company_name)
		.where(not_yet_evaluated)
		.order_by(order_column)
		.limit(limit)
	)
	rows = session.execute(stmt).all()
	candidates = [JobCandidate(job_id=row[0], job_url=row[1], job_role=row[2], company_name=row[3]) for row in rows]

	total_unevaluated_backlog = session.scalar(select(func.count()).select_from(JobListing).where(not_yet_evaluated)) or 0
	LOGGER.action(
		"jobs_to_process_selected",
		order=order,
		limit=limit,
		batch_count=len(candidates),
		total_unevaluated_backlog=total_unevaluated_backlog,
	)
	return candidates


@dataclass(frozen=True)
class JobResult:
	job_id: int
	match_score: int
	is_match: bool
	reasoning: str
	prompt_name: str
	prompt_version: str
	# The scoring logic identity behind prompt_version (see shared/job_match_data.py's
	# JobMatch.rubric_version) -- required, not defaulted, so every write site has to consciously
	# thread it through from its LoadedPrompt rather than silently persisting NULL going forward.
	rubric_version: int
	model_name: str
	score_breakdown: dict | None = None


def record_job_result(session: Session, result: JobResult) -> bool:
	"""Tool: idempotently persist a JobMatch row.

	`(job_id, prompt_version)` is the JobMatch primary key, so a duplicate write for the same
	job under the same prompt version (e.g. the same job picked up by two overlapping cycles,
	or a backfill run resumed after a partial failure) raises IntegrityError instead of
	double-writing; that's treated as a successful no-op rather than an error. A different
	prompt_version for the same job_id is a distinct row by design -- that's what lets a job
	carry both its original score and a rubric-based backfill score side by side.
	"""
	session.add(JobMatch(**asdict(result)))
	try:
		session.commit()
		return True
	except IntegrityError:
		session.rollback()
		LOGGER.action(
			"job_result_already_recorded",
			job_id=result.job_id,
			prompt_version=result.prompt_version,
			reason="duplicate JobMatch primary key (job_id, prompt_version)",
		)
		return False


@dataclass(frozen=True)
class ReprocessCandidate:
	job_id: int
	job_url: str | None
	job_role: str
	company_name: str


def get_reprocess_candidates(session: Session, *, target_prompt_version: str, limit: int) -> list[ReprocessCandidate]:
	"""Backfill tool: fetch up to `limit` jobs that already have a job_matches row under some
	prompt version but not yet under `target_prompt_version` -- see
	shared/job_match_data.py:reprocess_candidates_stmt for the priority ordering (match=true
	jobs first, then non-matches, oldest first within each group).
	"""
	rows = session.execute(reprocess_candidates_stmt(target_prompt_version=target_prompt_version, limit=limit)).all()
	candidates = [
		ReprocessCandidate(job_id=row.job_id, job_url=row.job_url, job_role=row.job_role, company_name=row.company_name)
		for row in rows
	]
	LOGGER.action(
		"reprocess_candidates_selected",
		target_prompt_version=target_prompt_version,
		limit=limit,
		batch_count=len(candidates),
	)
	return candidates
