from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from scraper import load_env_value


class Base(DeclarativeBase):
	pass


class JobListing(Base):
	__tablename__ = "job_listings"

	job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
	company_name: Mapped[str] = mapped_column(String(255), nullable=False)
	company_batch: Mapped[str | None] = mapped_column(String(50))
	company_url: Mapped[str | None] = mapped_column(Text)
	company_one_liner: Mapped[str | None] = mapped_column(Text)
	company_logo_url: Mapped[str | None] = mapped_column(Text)
	company_last_active_at: Mapped[str | None] = mapped_column(String(100))
	job_role: Mapped[str] = mapped_column(String(255), nullable=False)
	job_url: Mapped[str | None] = mapped_column(Text)
	application_link: Mapped[str | None] = mapped_column(Text)
	location: Mapped[str | None] = mapped_column(String(255))
	job_type: Mapped[str | None] = mapped_column(String(100))
	role_type: Mapped[str | None] = mapped_column(String(100))
	salary_range: Mapped[str | None] = mapped_column(String(100))
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=False),
		default=datetime.utcnow,
		onupdate=datetime.utcnow,
		nullable=False,
	)


JOB_FIELD_NAMES = (
	"company_name",
	"company_batch",
	"company_url",
	"company_one_liner",
	"company_logo_url",
	"company_last_active_at",
	"job_role",
	"job_url",
	"application_link",
	"location",
	"job_type",
	"role_type",
	"salary_range",
)


def normalize_database_url(database_url: str) -> str:
	if database_url.startswith("postgresql://"):
		return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
	if database_url.startswith("postgres://"):
		return database_url.replace("postgres://", "postgresql+psycopg://", 1)
	return database_url


def create_db_engine(database_url: str):
	return create_engine(normalize_database_url(database_url), future=True)


def normalize_job_payload(job: dict[str, object]) -> dict[str, str | None]:
	return {
		"company_name": str(job.get("company_name") or ""),
		"company_batch": job.get("company_batch") or None,
		"company_url": job.get("company_url") or None,
		"company_one_liner": job.get("company_one_liner") or None,
		"company_logo_url": job.get("company_logo_url") or None,
		"company_last_active_at": job.get("company_last_active_at") or None,
		"job_role": str(job.get("job_role") or ""),
		"job_url": job.get("job_url") or None,
		"application_link": job.get("application_link") or None,
		"location": job.get("location") or None,
		"job_type": job.get("job_type") or None,
		"role_type": job.get("role_type") or None,
		"salary_range": job.get("salary_range") or None,
	}


def apply_job_delta(listing: JobListing, payload: dict[str, str | None]) -> bool:
	changed = False
	for field_name in JOB_FIELD_NAMES:
		incoming_value = payload[field_name]
		if getattr(listing, field_name) != incoming_value:
			setattr(listing, field_name, incoming_value)
			changed = True

	return changed


def upsert_jobs(database_url: str, jobs: list[dict[str, object]]) -> int:
	engine = create_db_engine(database_url)
	Base.metadata.create_all(engine)
	job_records: list[tuple[int, dict[str, str | None]]] = []
	for job in jobs:
		job_id = job.get("job_id")
		if job_id is None:
			continue
		job_records.append((int(job_id), normalize_job_payload(job)))

	with Session(engine) as session:
		existing_job_ids = [job_id for job_id, _ in job_records]
		existing_listings = {
			listing.job_id: listing
			for listing in session.scalars(
				select(JobListing).where(JobListing.job_id.in_(existing_job_ids))
			)
		}
		delta_count = 0

		for job_id, payload in job_records:
			existing_listing = existing_listings.get(job_id)
			if existing_listing is None:
				session.add(JobListing(job_id=job_id, **payload))
				delta_count += 1
				continue

			if apply_job_delta(existing_listing, payload):
				delta_count += 1

		session.commit()

	return delta_count


def load_database_url() -> str:
	try:
		return load_env_value("DATABASE_URL")
	except KeyError:
		return load_env_value("POSTGRES_URL")


def run_write_stage(jobs: list[dict[str, Any]], database_url: str | None = None) -> int:
	resolved_database_url = database_url or load_database_url()
	return upsert_jobs(resolved_database_url, jobs)


def run_write_from_scrape_result(scrape_result: dict[str, Any], database_url: str | None = None) -> int:
	jobs = scrape_result.get("jobs", [])
	if not isinstance(jobs, list):
		raise ValueError("Scrape result must contain a list under 'jobs'")

	return run_write_stage(jobs, database_url)
