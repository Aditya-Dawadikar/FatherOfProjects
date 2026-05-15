from __future__ import annotations

import logging
import os
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"

from dataWriter import run_write_from_scrape_result
from scraper import run_scrape_stage


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


def load_schedule_config() -> tuple[int, str]:
	load_dotenv(ENV_FILE)
	interval_minutes = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))
	timezone = os.getenv("SCHEDULER_TIMEZONE", "UTC")
	if interval_minutes <= 0:
		raise ValueError("SCRAPE_INTERVAL_MINUTES must be greater than 0")

	return interval_minutes, timezone


def run_pipeline_job() -> None:
	LOGGER.info("Starting scrape stage")
	scrape_result = run_scrape_stage()
	LOGGER.info("Scrape completed with %s jobs", scrape_result["job_count"])

	LOGGER.info("Starting write stage")
	written_count = run_write_from_scrape_result(scrape_result)
	LOGGER.info("Write completed with %s upserts", written_count)


def build_scheduler() -> BlockingScheduler:
	interval_minutes, timezone = load_schedule_config()
	scheduler = BlockingScheduler(timezone=timezone)
	scheduler.add_job(
		run_pipeline_job,
		trigger="interval",
		minutes=interval_minutes,
		id="scrape_and_store_jobs",
		replace_existing=True,
		max_instances=1,
		coalesce=True,
	)
	LOGGER.info(
		"Scheduled scrape pipeline every %s minutes in timezone %s",
		interval_minutes,
		timezone,
	)
	return scheduler


def main() -> None:
	scheduler = build_scheduler()
	LOGGER.info("Starting APScheduler job runner")
	scheduler.start()


if __name__ == "__main__":
	main()
