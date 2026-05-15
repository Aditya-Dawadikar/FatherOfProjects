from __future__ import annotations

import logging
from typing import Any

from dataWriter import run_write_from_scrape_result
from scraper import run_scrape_stage
from stream_events import RedisStreamPublisher


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


def emit_pipeline_event(
	publisher: RedisStreamPublisher,
	event_type: str,
	stage: str,
	**payload: Any,
) -> None:
	publisher.publish(event_type=event_type, stage=stage, **payload)


def run_pipeline_job(publisher: RedisStreamPublisher) -> None:
	emit_pipeline_event(publisher, "pipeline_started", stage="pipeline")

	LOGGER.info("Starting scrape stage")
	emit_pipeline_event(publisher, "stage_started", stage="scrape")
	scrape_result = run_scrape_stage()
	LOGGER.info("Scrape completed with %s jobs", scrape_result["job_count"])
	emit_pipeline_event(
		publisher,
		"stage_completed",
		stage="scrape",
		target_url=scrape_result["url"],
		html_length=scrape_result["html_length"],
		job_count=scrape_result["job_count"],
	)

	LOGGER.info("Starting write stage")
	emit_pipeline_event(
		publisher,
		"stage_started",
		stage="write",
		job_count=scrape_result["job_count"],
	)
	written_count = run_write_from_scrape_result(scrape_result)
	LOGGER.info("Write completed with %s upserts", written_count)
	emit_pipeline_event(
		publisher,
		"stage_completed",
		stage="write",
		job_count=scrape_result["job_count"],
		written_count=written_count,
	)
	emit_pipeline_event(
		publisher,
		"pipeline_completed",
		stage="pipeline",
		job_count=scrape_result["job_count"],
		written_count=written_count,
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
