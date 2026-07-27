from __future__ import annotations

import logging
from typing import Any, Callable

from redis import Redis
from redis.exceptions import ResponseError

from env_utils import load_env_value


LOGGER = logging.getLogger(__name__)
DEFAULT_SOURCE_STREAM_NAME = "webscraper:events"
DEFAULT_CONSUMER_GROUP = "jobmanageragent-group"
DEFAULT_CONSUMER_NAME = "jobmanageragent-1"
TRIGGER_EVENT_TYPES = {"pipeline_completed"}
BLOCK_MS = 10_000


class RedisStreamConsumer:
	def __init__(self, redis_url: str, stream_name: str, group_name: str, consumer_name: str):
		self._client = Redis.from_url(redis_url, decode_responses=True)
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

	def run_forever(self, on_trigger: Callable[[dict[str, Any]], None]) -> None:
		self.ensure_group()
		LOGGER.info(
			"Listening on stream=%s group=%s consumer=%s",
			self._stream_name,
			self._group_name,
			self._consumer_name,
		)
		while True:
			response = self._client.xreadgroup(
				groupname=self._group_name,
				consumername=self._consumer_name,
				streams={self._stream_name: ">"},
				count=10,
				block=BLOCK_MS,
			)
			if not response:
				continue

			for _, entries in response:
				for entry_id, fields in entries:
					self._handle_entry(entry_id, fields, on_trigger)

	def _handle_entry(self, entry_id: str, fields: dict[str, str], on_trigger: Callable[[dict[str, Any]], None]) -> None:
		event_type = fields.get("event_type", "")
		try:
			if event_type in TRIGGER_EVENT_TYPES:
				LOGGER.info("Received trigger event_type=%s id=%s", event_type, entry_id)
				on_trigger(fields)
		except Exception:
			LOGGER.exception("Failed handling stream entry id=%s event_type=%s", entry_id, event_type)
		finally:
			self._client.xack(self._stream_name, self._group_name, entry_id)
