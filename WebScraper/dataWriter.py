from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scraper import load_env_value

from shared.job_data import (  # noqa: E402
	Base,
	DEFAULT_JOB_SOURCE,
	JobListing,
	apply_job_delta,
	create_db_engine,
	normalize_job_payload,
)


LOGGER = logging.getLogger(__name__)


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
				LOGGER.info("Inserting job_id=%s payload=%s", job_id, payload)
				session.add(
					JobListing(job_id=job_id, source_job_id=str(job_id), source=DEFAULT_JOB_SOURCE, **payload)
				)
				delta_count += 1
				continue

			if apply_job_delta(existing_listing, payload):
				LOGGER.info("Updating job_id=%s payload=%s", job_id, payload)
				delta_count += 1
			else:
				LOGGER.info("Skipping job_id=%s: already up to date, no fields changed", job_id)

		session.commit()

	skipped_count = len(job_records) - delta_count
	LOGGER.info(
		"upsert_jobs complete: received=%s inserted_or_updated=%s skipped_unchanged=%s",
		len(job_records),
		delta_count,
		skipped_count,
	)
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
