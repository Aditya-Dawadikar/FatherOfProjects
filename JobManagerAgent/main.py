from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent_logger import configure_logging, get_agent_logger, new_id
from matcher import run_matching_cycle
from mlflow_utils import get_tracking_uri
from stream_consumer import RedisStreamConsumer
from stream_events import RedisStreamPublisher, publish_event


ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

configure_logging()
LOGGER = get_agent_logger(__name__)


def run_cycle_safely(publisher: RedisStreamPublisher | None, *, reason: str) -> None:
	cycle_id = new_id()
	log = LOGGER.bind(cycle_id=cycle_id, reason=reason)
	log.action("cycle_triggered")
	publish_event(publisher, "matching_cycle_started", cycle_id=cycle_id, reason=reason)
	try:
		run_matching_cycle(publisher, cycle_id=cycle_id)
	except Exception as error:
		log.exception("Matching cycle failed")
		publish_event(
			publisher,
			"matching_cycle_failed",
			cycle_id=cycle_id,
			reason=reason,
			error_type=type(error).__name__,
			error_message=str(error),
		)


def main() -> None:
	publisher = RedisStreamPublisher.from_env()
	tracking_uri = get_tracking_uri()
	LOGGER.info("MLflow startup target uri=%s", tracking_uri)

	LOGGER.info("Running boot-time catch-up matching cycle")
	run_cycle_safely(publisher, reason="startup")

	consumer = RedisStreamConsumer.from_env()

	def on_trigger(_event_fields: dict[str, Any]) -> None:
		run_cycle_safely(publisher, reason="pipeline_completed")

	consumer.run_forever(on_trigger)


if __name__ == "__main__":
	main()
