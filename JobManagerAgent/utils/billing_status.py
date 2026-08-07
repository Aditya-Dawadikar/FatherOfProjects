"""Persistent flag for "the provider told us we're out of prepaid credits" (a 429
RESOURCE_EXHAUSTED carrying a billing-specific message, as opposed to an ordinary per-minute rate
limit that clears on its own -- see gemini_provider.py:_is_billing_exhausted_message).

Backed by Redis, not Postgres, mirroring RedisRpmLimiter and the primary-model cooldown flag
(rate_limiter.py, gemini_provider.py) -- this is operational state about "how is our current API
key doing", the same category of thing those already track, not an audit trail like
backfill_runs/prompt_active_history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from redis import Redis

from .env_utils import load_env_value


_KEY_PREFIX = "jobmanageragent:billing_status"
_EXHAUSTED_AT_KEY = f"{_KEY_PREFIX}:billing_exhausted_at"
_EXHAUSTED_MESSAGE_KEY = f"{_KEY_PREFIX}:billing_exhausted_message"

_CLIENT: Redis | None = None


def _client() -> Redis:
	global _CLIENT
	if _CLIENT is None:
		_CLIENT = Redis.from_url(load_env_value("REDIS_URL"), decode_responses=True)
	return _CLIENT


def record_billing_exhausted(message: str) -> None:
	"""Called the moment a 429 is identified as billing exhaustion (not an ordinary rate limit)
	-- persisted immediately, independent of whatever the caller that triggered it goes on to do
	with the raised BillingExhaustedError, so the dashboard alert doesn't depend on every call
	site remembering to report it.
	"""
	client = _client()
	now = datetime.now(timezone.utc).isoformat()
	client.set(_EXHAUSTED_AT_KEY, now)
	client.set(_EXHAUSTED_MESSAGE_KEY, message)


@dataclass(frozen=True)
class BillingStatus:
	is_billing_exhausted: bool
	billing_exhausted_at: str | None
	billing_exhausted_message: str | None


def get_billing_status() -> BillingStatus:
	client = _client()
	exhausted_at = client.get(_EXHAUSTED_AT_KEY)
	return BillingStatus(
		is_billing_exhausted=exhausted_at is not None,
		billing_exhausted_at=exhausted_at,
		billing_exhausted_message=client.get(_EXHAUSTED_MESSAGE_KEY),
	)


def reset_billing_status() -> None:
	"""Clears the billing-exhausted flag -- an explicit operator action ("I've addressed it"),
	not something inferred automatically from a successful call, since a successful call after
	exhaustion could just as easily mean a different, unaffected API key was swapped in rather
	than the same project's credits being topped up.
	"""
	_client().delete(_EXHAUSTED_AT_KEY, _EXHAUSTED_MESSAGE_KEY)
