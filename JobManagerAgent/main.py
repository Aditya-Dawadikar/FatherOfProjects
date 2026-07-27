from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from matcher import run_matching_cycle
from stream_consumer import RedisStreamConsumer
from stream_events import RedisStreamPublisher, publish_event


ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


def run_cycle_safely(publisher: RedisStreamPublisher | None, *, reason: str) -> None:
	LOGGER.info("Starting matching cycle (reason=%s)", reason)
	publish_event(publisher, "matching_cycle_started", reason=reason)
	try:
		run_matching_cycle(publisher)
	except Exception as error:
		LOGGER.exception("Matching cycle failed (reason=%s)", reason)
		publish_event(
			publisher,
			"matching_cycle_failed",
			reason=reason,
			error_type=type(error).__name__,
			error_message=str(error),
		)


def main() -> None:
	publisher = RedisStreamPublisher.from_env()

	LOGGER.info("Running boot-time catch-up matching cycle")
	run_cycle_safely(publisher, reason="startup")

	consumer = RedisStreamConsumer.from_env()

	def on_trigger(_event_fields: dict[str, Any]) -> None:
		run_cycle_safely(publisher, reason="pipeline_completed")

	consumer.run_forever(on_trigger)


if __name__ == "__main__":
	main()
