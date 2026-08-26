from __future__ import annotations

import logging
from typing import Any

from ats_scraper import RETENTION_MAX_AGE_DAYS, RETENTION_SOURCES, run_scrape_stage_for_source
from dataWriter import run_purge_stage, run_write_stage
from scraper import run_scrape_stage
from stream_events import RedisStreamPublisher


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)

# Every source this pipeline scrapes per run, in order. YC keeps its own dedicated scrape_stage
# (single TARGET_URL, HTML scrape); the other three are API-based and share ats_scraper.py's
# generic per-source runner (each reads its own comma-separated board-slugs env var -- see
# ats_scraper.py's _FETCHERS). Adding a fifth source is just adding one more entry here plus a
# fetch_<source>_jobs function in ats_scraper.py -- no other pipeline change needed.
_SOURCES: tuple[tuple[str, Any], ...] = (
	("ycombinator", run_scrape_stage),
	("greenhouse", lambda: run_scrape_stage_for_source("greenhouse")),
	("ashby", lambda: run_scrape_stage_for_source("ashby")),
	("lever", lambda: run_scrape_stage_for_source("lever")),
)


def emit_pipeline_event(
	publisher: RedisStreamPublisher,
	event_type: str,
	stage: str,
	**payload: Any,
) -> None:
	publisher.publish(event_type=event_type, stage=stage, **payload)


def run_pipeline_job(publisher: RedisStreamPublisher) -> None:
	emit_pipeline_event(publisher, "pipeline_started", stage="pipeline")

	total_scraped = 0
	total_written = 0
	for source_name, scrape_fn in _SOURCES:
		LOGGER.info("Starting scrape stage: %s", source_name)
		emit_pipeline_event(publisher, "stage_started", stage=f"scrape:{source_name}")
		scrape_result = scrape_fn()
		job_count = scrape_result["job_count"]
		LOGGER.info("%s scrape completed with %s jobs", source_name, job_count)
		emit_pipeline_event(
			publisher,
			"stage_completed",
			stage=f"scrape:{source_name}",
			job_count=job_count,
		)

		LOGGER.info("Starting write stage: %s", source_name)
		emit_pipeline_event(publisher, "stage_started", stage=f"write:{source_name}", job_count=job_count)
		written_count = run_write_stage(scrape_result["jobs"])
		LOGGER.info("%s write completed with %s upserts", source_name, written_count)
		emit_pipeline_event(
			publisher,
			"stage_completed",
			stage=f"write:{source_name}",
			job_count=job_count,
			written_count=written_count,
		)
		total_scraped += job_count
		total_written += written_count

	LOGGER.info("Starting purge stage: %s older than %s day(s)", RETENTION_SOURCES, RETENTION_MAX_AGE_DAYS)
	emit_pipeline_event(publisher, "stage_started", stage="purge")
	purged_count = run_purge_stage(sources=RETENTION_SOURCES, max_age_days=RETENTION_MAX_AGE_DAYS)
	LOGGER.info("Purge completed: %s row(s) deleted", purged_count)
	emit_pipeline_event(publisher, "stage_completed", stage="purge", purged_count=purged_count)

	emit_pipeline_event(
		publisher,
		"pipeline_completed",
		stage="pipeline",
		job_count=total_scraped,
		written_count=total_written,
		purged_count=purged_count,
	)


def main() -> None:
	LOGGER.info("Starting one-shot scrape pipeline")
	publisher = RedisStreamPublisher.from_env()
	try:
		run_pipeline_job(publisher)
	except Exception as error:
		emit_pipeline_event(
			publisher,
			"pipeline_failed",
			stage="pipeline",
			error_type=type(error).__name__,
			error_message=str(error),
		)
		raise


if __name__ == "__main__":
	main()
