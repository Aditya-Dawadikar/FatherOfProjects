from __future__ import annotations

import logging

from dataWriter import run_write_from_scrape_result
from scraper import run_scrape_stage


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


def run_pipeline_job() -> None:
	LOGGER.info("Starting scrape stage")
	scrape_result = run_scrape_stage()
	LOGGER.info("Scrape completed with %s jobs", scrape_result["job_count"])

	LOGGER.info("Starting write stage")
	written_count = run_write_from_scrape_result(scrape_result)
	LOGGER.info("Write completed with %s upserts", written_count)


def main() -> None:
	LOGGER.info("Starting one-shot scrape pipeline")
	run_pipeline_job()


if __name__ == "__main__":
	main()
