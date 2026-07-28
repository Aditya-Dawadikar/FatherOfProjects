from __future__ import annotations

from typing import Any, Callable

from redis import Redis
from redis.exceptions import ConnectionError, ResponseError, TimeoutError

from utils.agent_logger import get_agent_logger
from utils.env_utils import load_env_value


LOGGER = get_agent_logger(__name__)
DEFAULT_SOURCE_STREAM_NAME = "webscraper:events"
DEFAULT_CONSUMER_GROUP = "jobmanageragent-group"
DEFAULT_CONSUMER_NAME = "jobmanageragent-1"
TRIGGER_EVENT_TYPES = {"pipeline_completed"}
BLOCK_MS = 10_000


class RedisStreamConsumer:
	def __init__(self, redis_url: str, stream_name: str, group_name: str, consumer_name: str):
		self._client = Redis.from_url(
			redis_url,
			decode_responses=True,
			socket_keepalive=True,
			health_check_interval=30,
		)
		self._stream_name = stream_name
		self._group_name = group_name
		self._consumer_name = consumer_name

	@classmethod
	def from_env(cls) -> "RedisStreamConsumer":
		redis_url = load_env_value("REDIS_URL")
		stream_name = load_env_value("WEBSCRAPER_REDIS_STREAM_NAME", DEFAULT_SOURCE_STREAM_NAME)
		group_name = load_env_value("JOB_MANAGER_CONSUMER_GROUP", DEFAULT_CONSUMER_GROUP)
		consumer_name = load_env_value("JOB_MANAGER_CONSUMER_NAME", DEFAULT_CONSUMER_NAME)
		return cls(redis_url, stream_name, group_name, consumer_name)

	def ensure_group(self) -> None:
		try:
			self._client.xgroup_create(name=self._stream_name, groupname=self._group_name, id="$", mkstream=True)
			LOGGER.info("Created consumer group %s on stream %s", self._group_name, self._stream_name)
		except ResponseError as error:
			if "BUSYGROUP" not in str(error):
				raise
			LOGGER.info("Consumer group %s already exists on stream %s", self._group_name, self._stream_name)

	def run_forever(
		self,
		on_trigger: Callable[[dict[str, Any]], None],
		on_idle: Callable[[], None] | None = None,
	) -> None:
		"""Blocks up to BLOCK_MS waiting for a `pipeline_completed` event and handles it via
		`on_trigger`. When the block times out with nothing to read, the agent isn't idle -- it
		calls `on_idle` (if given) to do one unit of backfill work on the historical backlog
		before polling again, so it stays continuously occupied instead of doing nothing between
		live triggers.
		"""
		self.ensure_group()
		LOGGER.info(
			"Listening on stream=%s group=%s consumer=%s",
			self._stream_name,
			self._group_name,
			self._consumer_name,
		)
		while True:
			try:
				response = self._client.xreadgroup(
					groupname=self._group_name,
					consumername=self._consumer_name,
					streams={self._stream_name: ">"},
					count=10,
					block=BLOCK_MS,
				)
			except (TimeoutError, ConnectionError):
				LOGGER.warning(
					"Redis connection dropped/timed out while blocking on stream=%s; reconnecting",
					self._stream_name,
				)
				continue
			if not response:
				if on_idle is not None:
					self._handle_idle(on_idle)
				continue

			for _, entries in response:
				for entry_id, fields in entries:
					self._handle_entry(entry_id, fields, on_trigger)

	def _handle_idle(self, on_idle: Callable[[], None]) -> None:
		try:
			on_idle()
		except Exception:
			LOGGER.exception("Backfill idle tick failed")

	def _handle_entry(self, entry_id: str, fields: dict[str, str], on_trigger: Callable[[dict[str, Any]], None]) -> None:
		event_type = fields.get("event_type", "")
		other_fields = {key: value for key, value in fields.items() if key != "event_type"}
		LOGGER.event_received(event_type=event_type, entry_id=entry_id, stream=self._stream_name, **other_fields)
		try:
			if event_type in TRIGGER_EVENT_TYPES:
				LOGGER.action("trigger_matching_cycle", event_type=event_type, entry_id=entry_id)
				on_trigger(fields)
			else:
				LOGGER.action("ignore_event", event_type=event_type, entry_id=entry_id, reason="not a trigger event_type")
		except Exception:
			LOGGER.exception("Failed handling stream entry id=%s event_type=%s", entry_id, event_type)
		finally:
			self._client.xack(self._stream_name, self._group_name, entry_id)
