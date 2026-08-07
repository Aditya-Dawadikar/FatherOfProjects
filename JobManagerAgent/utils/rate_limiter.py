from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

from langchain_core.rate_limiters import BaseRateLimiter
from redis import Redis

from .agent_logger import get_agent_logger
from .config import BACKFILL_RPM_CAP, DEFAULT_RPM_CAP, EVAL_RPM_CAP, WINDOW_SECONDS
from .env_utils import load_env_value


LOGGER = get_agent_logger(__name__)

@dataclass(frozen=True)
class RpmUsage:
	"""One bucket's current standing against its RPM cap, as of the moment it was read --
	returned by RedisRpmLimiter.current_usage(), the read-only counterpart to acquire()."""

	bucket: str
	model: str
	count: int
	cap: int

	@property
	def remaining(self) -> int:
		return max(0, self.cap - self.count)


# Every bucket this codebase tracks, in the order the x+y+z+w model documents them in
# utils/config.py -- the single source of truth GET /admin/rate-limits iterates to build the
# dashboard's RPM breakdown, so a new bucket only needs to be added here (plus a cap loader) to
# show up there automatically.
RPM_BUCKETS: tuple[str, ...] = ("live", "backfill", "eval")
_RPM_CONFIG_KEY_PREFIX = "jobmanageragent:rpm_config"


def _rpm_config_key(model: str) -> str:
	return f"{_RPM_CONFIG_KEY_PREFIX}:{model}"


def _override_client() -> Redis:
	return Redis.from_url(load_env_value("REDIS_URL"), decode_responses=True)


def _load_bucket_override(model: str, bucket: str) -> int | None:
	field = f"{bucket}_cap"
	value = _override_client().hget(_rpm_config_key(model), field)
	if value is None or not value.strip():
		return None
	return int(value)


def load_provider_quota_override(model: str) -> int | None:
	value = _override_client().hget(_rpm_config_key(model), "provider_quota")
	if value is None or not value.strip():
		return None
	return int(value)


def set_rpm_distribution(
	model: str,
	*,
	live_cap: int,
	backfill_cap: int,
	eval_cap: int,
	provider_quota: int | None,
) -> None:
	fields = {
		"live_cap": str(live_cap),
		"backfill_cap": str(backfill_cap),
		"eval_cap": str(eval_cap),
	}
	client = _override_client()
	key = _rpm_config_key(model)
	client.hset(key, mapping=fields)
	if provider_quota is None:
		client.hdel(key, "provider_quota")
	else:
		client.hset(key, "provider_quota", str(provider_quota))


def _cap_env_key(model: str, *, suffix: str = "") -> str:
	base = f"LLM_RPM_CAP__{model.upper().replace('-', '_').replace('.', '_')}"
	return f"{base}__{suffix}" if suffix else base


def load_rpm_cap(model: str) -> int:
	override = _load_bucket_override(model, "live")
	if override is not None:
		return override
	return int(load_env_value(_cap_env_key(model), str(DEFAULT_RPM_CAP)))


def load_backfill_rpm_cap(model: str) -> int:
	"""Reserved RPM budget for the "backfill" bucket, deliberately small and kept separate from
	load_rpm_cap's "live" budget for the same model (see RedisRpmLimiter.acquire's `bucket`
	param) -- this is what lets a large rescore-under-a-new-prompt backfill run without ever
	crowding out live scoring's share of the model's real external quota.
	"""
	override = _load_bucket_override(model, "backfill")
	if override is not None:
		return override
	return int(load_env_value(_cap_env_key(model, suffix="BACKFILL"), str(BACKFILL_RPM_CAP)))


def load_eval_rpm_cap(model: str) -> int:
	"""Reserved RPM budget for the "eval" bucket -- kept separate from "live" so a triggered
	offline eval run (potentially scoring the full golden dataset) can't compete with real live
	traffic for the same counter. See utils/config.py's x+y+z+w budget model.
	"""
	override = _load_bucket_override(model, "eval")
	if override is not None:
		return override
	return int(load_env_value(_cap_env_key(model, suffix="EVAL"), str(EVAL_RPM_CAP)))


def load_cap_for_bucket(model: str, bucket: str) -> int:
	if bucket == "backfill":
		return load_backfill_rpm_cap(model)
	if bucket == "eval":
		return load_eval_rpm_cap(model)
	return load_rpm_cap(model)


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

	def _key(self, model: str, bucket: str) -> str:
		return f"{self._key_prefix}:{model}:{bucket}"

	def current_usage(self, model: str, bucket: str, *, cap: int | None = None) -> "RpmUsage":
		"""Read-only peek at a bucket's current sliding-window count -- trims expired entries
		(same window logic as acquire()) but never adds one, so calling this to render a
		dashboard never itself consumes budget. Used by GET /admin/rate-limits.
		"""
		effective_cap = cap if cap is not None else load_cap_for_bucket(model, bucket)
		key = self._key(model, bucket)
		now = time.time()
		self._client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
		count = self._client.zcard(key)
		return RpmUsage(bucket=bucket, model=model, count=int(count), cap=effective_cap)

	def acquire(self, model: str, *, cap: int | None = None, bucket: str = "live") -> float:
		"""Blocks (sleeping) until a call slot for `model` is available under its RPM cap,
		reserves the slot, then returns. Returns total seconds spent waiting.

		`bucket` picks an independent sliding-window counter within the same model's budget --
		"live" (the default, used by the live/backfill-unscored cycle and the ReAct agent) and
		"backfill" (used by the rescore-under-a-new-prompt backfill process, see
		utils/config.py:BACKFILL_RPM_CAP) never share a counter, so a large backfill run can
		never starve live scoring of RPM headroom by filling the same window. Each bucket's cap
		is a slice of the model's real external quota, not additive on top of it -- see
		BACKFILL_RPM_CAP's definition for the accounting.
		"""
		effective_cap = cap if cap is not None else load_rpm_cap(model)
		key = self._key(model, bucket)
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
	acquire -- current_usage() is a read-only peek that never reserves a slot, a different thing
	entirely) rather than faked with a wrong answer.
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
