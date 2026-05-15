from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from scraper import load_env_value


LOGGER = logging.getLogger(__name__)
DEFAULT_STREAM_NAME = "webscraper:events"


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_stream_value(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, (int, float, str)):
		return str(value)
	return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


class RedisStreamPublisher:
	def __init__(self, redis_url: str, stream_name: str = DEFAULT_STREAM_NAME):
		self._stream_name = stream_name
		self._client = Redis.from_url(redis_url, decode_responses=True)

	@classmethod
	def from_env(cls) -> "RedisStreamPublisher":
		redis_url = load_env_value("REDIS_URL")
		try:
			stream_name = load_env_value("REDIS_STREAM_NAME")
		except KeyError:
			stream_name = DEFAULT_STREAM_NAME
		return cls(redis_url=redis_url, stream_name=stream_name)

	def publish(self, event_type: str, **payload: Any) -> str:
		fields = {
			"event_type": event_type,
			"emitted_at": utc_now_iso(),
		}
		fields.update({key: serialize_stream_value(value) for key, value in payload.items()})

		try:
			message_id = self._client.xadd(self._stream_name, fields)
		except RedisError:
			LOGGER.exception("Failed to publish event_type=%s to Redis stream %s", event_type, self._stream_name)
			raise

		LOGGER.info(
			"Published event_type=%s to Redis stream %s with id=%s",
			event_type,
			self._stream_name,
			message_id,
		)
		return message_id