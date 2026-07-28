from __future__ import annotations

import asyncio
import time
import uuid

from langchain_core.rate_limiters import BaseRateLimiter
from redis import Redis

from .agent_logger import get_agent_logger
from .env_utils import load_env_value


LOGGER = get_agent_logger(__name__)

DEFAULT_RPM_CAP = 4
WINDOW_SECONDS = 60.0


def _cap_env_key(model: str) -> str:
	return f"LLM_RPM_CAP__{model.upper().replace('-', '_').replace('.', '_')}"


def load_rpm_cap(model: str) -> int:
	return int(load_env_value(_cap_env_key(model), str(DEFAULT_RPM_CAP)))


class RedisRpmLimiter:
	"""Sliding-window requests-per-minute limiter, one budget per model, backed by Redis so
	the same budget is shared across process restarts and across every call site (live
	cycles, backfill cycles, offline evals) instead of each tracking its own local counter.

	The real per-model Gemini quota is shared with another application on the same project,
	so this limiter is deliberately proactive: it paces calls to stay under a self-imposed
	cap below the real ceiling, rather than reacting to 429s after the budget is already
	blown for that window.
	"""

	def __init__(self, client: Redis | None = None, *, key_prefix: str = "jobmanageragent:llm_rpm") -> None:
		self._client = client or Redis.from_url(load_env_value("REDIS_URL"), decode_responses=True)
		self._key_prefix = key_prefix

	def _key(self, model: str) -> str:
		return f"{self._key_prefix}:{model}"

	def acquire(self, model: str, *, cap: int | None = None) -> float:
		"""Blocks (sleeping) until a call slot for `model` is available under its RPM cap,
		reserves the slot, then returns. Returns total seconds spent waiting."""
		effective_cap = cap if cap is not None else load_rpm_cap(model)
		key = self._key(model)
		waited = 0.0

		while True:
			now = time.time()
			window_start = now - WINDOW_SECONDS
			self._client.zremrangebyscore(key, 0, window_start)
			count = self._client.zcard(key)

			if count < effective_cap:
				self._client.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
				self._client.expire(key, int(WINDOW_SECONDS) + 5)
				return waited

			oldest = self._client.zrange(key, 0, 0, withscores=True)
			sleep_for = 1.0
			if oldest:
				_, oldest_ts = oldest[0]
				sleep_for = max(0.5, (oldest_ts + WINDOW_SECONDS) - now)

			LOGGER.action(
				"llm_rpm_budget_wait",
				model=model,
				cap=effective_cap,
				in_window=count,
				sleep_seconds=round(sleep_for, 1),
			)
			time.sleep(sleep_for)
			waited += sleep_for


class LangChainRedisRpmLimiter(BaseRateLimiter):
	"""Adapts RedisRpmLimiter to LangChain's `rate_limiter=` hook on BaseChatModel, so a
	ChatGoogleGenerativeAI instance draws from the exact same per-model Redis RPM budget as the
	non-agentic call path in gemini_provider.py -- there is one budget per model, not one per
	code path that happens to call the provider.

	Every LangChain call site invokes `acquire`/`aacquire` with `blocking=True`, so the
	`blocking=False` case is intentionally unimplemented (RedisRpmLimiter has no non-blocking
	peek) rather than faked with a wrong answer.
	"""

	def __init__(self, model: str, limiter: RedisRpmLimiter | None = None) -> None:
		self._model = model
		self._limiter = limiter or RedisRpmLimiter()

	def acquire(self, *, blocking: bool = True) -> bool:
		if not blocking:
			raise NotImplementedError("LangChainRedisRpmLimiter only supports blocking acquisition")
		self._limiter.acquire(self._model)
		return True

	async def aacquire(self, *, blocking: bool = True) -> bool:
		if not blocking:
			raise NotImplementedError("LangChainRedisRpmLimiter only supports blocking acquisition")
		# RedisRpmLimiter.acquire is a synchronous, sleep-based blocking call; run it off the
		# event loop so an async caller doesn't stall other concurrent work while waiting.
		await asyncio.to_thread(self._limiter.acquire, self._model)
		return True
