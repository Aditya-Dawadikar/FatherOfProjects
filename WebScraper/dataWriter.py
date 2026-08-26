from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scraper import load_env_value

from shared.job_data import (  # noqa: E402
	Base,
	JobListing,
	apply_job_delta,
	create_db_engine,
	normalize_job_payload,
)


LOGGER = logging.getLogger(__name__)


def upsert_jobs(database_url: str, jobs: list[dict[str, object]]) -> int:
	"""Upserts jobs from any source, keyed on (source, source_job_id) -- job_listings' actual
	uniqueness key (see shared/job_data.py) now that YC is no longer the only source and a bare
	numeric/string id can't be assumed globally unique across Ashby/Greenhouse/Lever/YC. Every job
	dict must carry its own "source" and "source_job_id" (each source's fetcher sets these --
	scraper.py for YC, ashby_scraper.py/greenhouse_scraper.py/lever_scraper.py for the others).
	"""
	engine = create_db_engine(database_url)
	Base.metadata.create_all(engine)
	job_records: list[tuple[str, str, dict[str, str | None]]] = []
	for job in jobs:
		source = job.get("source")
		source_job_id = job.get("source_job_id")
		if not source or not source_job_id:
			LOGGER.warning("Skipping job with missing source/source_job_id: %s", job)
			continue
		job_records.append((str(source), str(source_job_id), normalize_job_payload(job)))

	with Session(engine) as session:
		existing_listings: dict[tuple[str, str], JobListing] = {}
		if job_records:
			sources = {source for source, _, _ in job_records}
			candidates = session.scalars(select(JobListing).where(JobListing.source.in_(sources)))
			existing_listings = {(listing.source, listing.source_job_id): listing for listing in candidates}
		delta_count = 0

		for source, source_job_id, payload in job_records:
			key = (source, source_job_id)
			existing_listing = existing_listings.get(key)
			if existing_listing is None:
				LOGGER.info("Inserting source=%s source_job_id=%s payload=%s", source, source_job_id, payload)
				session.add(JobListing(source=source, source_job_id=source_job_id, **payload))
				delta_count += 1
				continue

			if apply_job_delta(existing_listing, payload):
				LOGGER.info("Updating source=%s source_job_id=%s payload=%s", source, source_job_id, payload)
				delta_count += 1
			else:
				LOGGER.info("Skipping source=%s source_job_id=%s: already up to date, no fields changed", source, source_job_id)

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
