from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.orm import Session

from scraper import load_env_value

from shared.job_data import (  # noqa: E402
	Base,
	JobListing,
	apply_job_delta,
	create_db_engine,
	load_job_table_name,
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


def purge_stale_jobs(database_url: str, *, sources: tuple[str, ...], max_age_days: int) -> int:
	"""Deletes job_listings rows (and their job_matches, if any) for `sources` whose updated_at is
	older than `max_age_days`. See ats_scraper.py's RECENCY_WINDOW_HOURS/RETENTION_MAX_AGE_DAYS
	docstring for why this exists: a job outside the scrape's recency window never gets re-written
	(each source's own timestamp only moves forward, so a future scrape's recency filter keeps
	excluding it too), so its updated_at here freezes at ingestion time and correctly reflects
	"not seen in a scrape since" -- keeping it around indefinitely only grows JobManagerAgent's
	backlog for no benefit.

	job_matches has no ON DELETE CASCADE on its job_listing_id FK (see JobManagerAgent's
	scripts/migrations/0004_add_job_listing_id_to_job_matches.py), so any match rows for a purged
	listing are deleted first via raw SQL -- WebScraper has no JobMatch model of its own (it never
	otherwise touches that table), so this reaches it by table name instead of importing one.
	"""
	engine = create_db_engine(database_url)
	job_table = load_job_table_name()
	match_table = os.getenv("JOB_MATCH_TABLE_NAME", "job_matches").strip() or "job_matches"
	cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max_age_days)

	with Session(engine) as session:
		stale_ids = list(
			session.scalars(
				select(JobListing.id).where(JobListing.source.in_(sources), JobListing.updated_at < cutoff)
			)
		)
		if not stale_ids:
			LOGGER.info("purge_stale_jobs: no %s rows older than %s day(s)", sources, max_age_days)
			return 0

		session.execute(
			text(f'DELETE FROM "{match_table}" WHERE job_listing_id IN :ids').bindparams(
				bindparam("ids", expanding=True)
			),
			{"ids": stale_ids},
		)
		session.execute(delete(JobListing).where(JobListing.id.in_(stale_ids)))
		session.commit()

	LOGGER.info("purge_stale_jobs: deleted %s row(s) from %s older than %s day(s)", len(stale_ids), sources, max_age_days)
	return len(stale_ids)


def load_database_url() -> str:
	try:
		return load_env_value("DATABASE_URL")
	except KeyError:
		return load_env_value("POSTGRES_URL")


def run_write_stage(jobs: list[dict[str, Any]], database_url: str | None = None) -> int:
	resolved_database_url = database_url or load_database_url()
	return upsert_jobs(resolved_database_url, jobs)


def run_purge_stage(*, sources: tuple[str, ...], max_age_days: int, database_url: str | None = None) -> int:
	resolved_database_url = database_url or load_database_url()
	return purge_stale_jobs(resolved_database_url, sources=sources, max_age_days=max_age_days)


def run_write_from_scrape_result(scrape_result: dict[str, Any], database_url: str | None = None) -> int:
	jobs = scrape_result.get("jobs", [])
	if not isinstance(jobs, list):
		raise ValueError("Scrape result must contain a list under 'jobs'")

	return run_write_stage(jobs, database_url)
