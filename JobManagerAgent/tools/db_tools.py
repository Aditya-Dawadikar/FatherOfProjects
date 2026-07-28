from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.job_data import JobListing
from shared.job_match_data import JobMatch


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
	stmt = (
		select(JobListing.job_id, JobListing.job_url, JobListing.job_role, JobListing.company_name)
		.where(JobListing.job_id.notin_(select(JobMatch.job_id)))
		.order_by(order_column)
		.limit(limit)
	)
	rows = session.execute(stmt).all()
	return [JobCandidate(job_id=row[0], job_url=row[1], job_role=row[2], company_name=row[3]) for row in rows]


@dataclass(frozen=True)
class JobResult:
	job_id: int
	match_score: int
	is_match: bool
	reasoning: str
	prompt_name: str
	prompt_version: str
	model_name: str


def record_job_result(session: Session, result: JobResult) -> bool:
	"""Tool: idempotently persist a JobMatch row.

	`job_id` is the JobMatch primary key, so a duplicate write (e.g. the same job picked up
	by two overlapping cycles) raises IntegrityError instead of double-writing; that's treated
	as a successful no-op -- the job is already recorded -- rather than an error.
	"""
	session.add(JobMatch(**asdict(result)))
	try:
		session.commit()
		return True
	except IntegrityError:
		session.rollback()
		return False
