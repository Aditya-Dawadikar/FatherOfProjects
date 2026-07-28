from __future__ import annotations

from typing import Any

from agents import run_matching_cycle_with_agent
from integrations.streaming import RedisStreamConsumer, RedisStreamPublisher, publish_event
from utils.agent_logger import get_agent_logger, new_id


LOGGER = get_agent_logger(__name__)


def run_cycle_safely(publisher: RedisStreamPublisher | None, *, reason: str, mode: str = "live") -> None:
	cycle_id = new_id()
	log = LOGGER.bind(cycle_id=cycle_id, reason=reason, mode=mode)
	log.action("cycle_triggered")
	publish_event(publisher, "matching_cycle_started", cycle_id=cycle_id, reason=reason, mode=mode)
	try:
		run_matching_cycle_with_agent(publisher, cycle_id=cycle_id, mode=mode)
	except Exception as error:
		log.exception("Matching cycle failed")
		publish_event(
			publisher,
			"matching_cycle_failed",
			cycle_id=cycle_id,
			reason=reason,
			mode=mode,
			error_type=type(error).__name__,
			error_message=str(error),
		)


def run_agent_worker(publisher: RedisStreamPublisher | None) -> None:
	"""Runs forever: boot-time catch-up, then blocks on the Redis stream consumer group,
	triggering a live cycle per pipeline_completed event and a backfill cycle on every idle
	timeout. This is the entire body of what used to be main.py -- unchanged behavior, just run
	on a background thread (see api/app.py's lifespan) so the process can serve HTTP at the same
	time instead of this being the whole process.
	"""
	LOGGER.info("Running boot-time catch-up matching cycle")
	run_cycle_safely(publisher, reason="startup", mode="live")

	consumer = RedisStreamConsumer.from_env()

	def on_trigger(_event_fields: dict[str, Any]) -> None:
		run_cycle_safely(publisher, reason="pipeline_completed", mode="live")

	def on_idle() -> None:
		# Nothing new arrived from the scraper -- rather than sit idle, spend this tick
		# draining the oldest unprocessed jobs in job_listings (see react_agent.py mode="backfill"),
		# so historical backlog always makes progress whenever there's no live work to do.
		run_cycle_safely(publisher, reason="idle_backfill", mode="backfill")

	consumer.run_forever(on_trigger, on_idle)
