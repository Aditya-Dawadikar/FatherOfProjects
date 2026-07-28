from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from agents import run_matching_cycle_with_agent
from core import run_matching_cycle
from integrations.streaming import RedisStreamConsumer, RedisStreamPublisher, publish_event
from utils.agent_logger import configure_logging, get_agent_logger, new_id
from utils.env_utils import ENV_FILE, load_env_value
from utils.mlflow_utils import get_tracking_uri


load_dotenv(ENV_FILE)

configure_logging()
LOGGER = get_agent_logger(__name__)

# MATCHING_ENGINE selects which cycle implementation live/backfill triggers run:
# "deterministic" (default) is the tested, production-proven fixed Python loop in matcher.py.
# "react_agent" is the LangGraph ReAct agent in react_agent.py, where the LLM itself drives
# tool calls (get_jobs_to_process/record_job_result) rather than a fixed loop calling them --
# not yet run against production Postgres, so it isn't the default.
_ENGINES = {
	"deterministic": run_matching_cycle,
	"react_agent": run_matching_cycle_with_agent,
}


def load_matching_engine() -> str:
	name = load_env_value("MATCHING_ENGINE", "deterministic").strip().lower()
	if name not in _ENGINES:
		raise ValueError(f"Unsupported MATCHING_ENGINE {name!r}; expected one of {sorted(_ENGINES)}")
	return name


def run_cycle_safely(publisher: RedisStreamPublisher | None, *, reason: str, mode: str = "live") -> None:
	cycle_id = new_id()
	engine_name = load_matching_engine()
	run_cycle = _ENGINES[engine_name]
	log = LOGGER.bind(cycle_id=cycle_id, reason=reason, mode=mode, engine=engine_name)
	log.action("cycle_triggered")
	publish_event(publisher, "matching_cycle_started", cycle_id=cycle_id, reason=reason, mode=mode, engine=engine_name)
	try:
		run_cycle(publisher, cycle_id=cycle_id, mode=mode)
	except Exception as error:
		log.exception("Matching cycle failed")
		publish_event(
			publisher,
			"matching_cycle_failed",
			cycle_id=cycle_id,
			reason=reason,
			mode=mode,
			engine=engine_name,
			error_type=type(error).__name__,
			error_message=str(error),
		)


def main() -> None:
	publisher = RedisStreamPublisher.from_env()
	tracking_uri = get_tracking_uri()
	LOGGER.info("MLflow startup target uri=%s", tracking_uri)

	LOGGER.info("Running boot-time catch-up matching cycle")
	run_cycle_safely(publisher, reason="startup", mode="live")

	consumer = RedisStreamConsumer.from_env()

	def on_trigger(_event_fields: dict[str, Any]) -> None:
		run_cycle_safely(publisher, reason="pipeline_completed", mode="live")

	def on_idle() -> None:
		# Nothing new arrived from the scraper -- rather than sit idle, spend this tick
		# draining the oldest unprocessed jobs in job_listings (see matcher.py mode="backfill"),
		# so historical backlog always makes progress whenever there's no live work to do.
		run_cycle_safely(publisher, reason="idle_backfill", mode="backfill")

	consumer.run_forever(on_trigger, on_idle)


if __name__ == "__main__":
	main()
