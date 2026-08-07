"""Operator control over the never-scored-jobs backfill (mode="backfill" cycles, triggered by
integrations/streaming/stream_consumer.py's idle timeout via api/agent_worker.py's on_idle) --
NOT the backfill/ package's rescore-under-a-new-prompt-version process, which is a separate,
explicitly-triggered mechanism (see docs/backfill-design.md for why the two are kept orthogonal).

This exists so a prompt cutover can be driven as a predictable sequence -- pause here, promote
the new prompt version (POST /admin/active-prompt), resume here -- rather than only relying on
get_active_prompt() re-resolving the 'production' alias fresh on every cycle. That re-resolution
alone is enough for correctness (see prompt_registry.py's docstring), but pausing gives an
operator a clean window with zero backfill-mode cycles in flight while the switch happens.
"""

from __future__ import annotations

from redis import Redis

from .env_utils import load_env_value


_UNSCORED_BACKFILL_PAUSE_KEY = "jobmanageragent:unscored_backfill:paused"


def _client() -> Redis:
	return Redis.from_url(load_env_value("REDIS_URL"), decode_responses=True)


def unscored_backfill_pause_reason() -> str | None:
	"""Read fresh from Redis on every call (no local/process caching) so a pause or resume takes
	effect on the very next idle tick anywhere in the fleet, not after a process restart."""
	return _client().get(_UNSCORED_BACKFILL_PAUSE_KEY)


def is_unscored_backfill_paused() -> bool:
	return unscored_backfill_pause_reason() is not None


def pause_unscored_backfill(*, reason: str) -> None:
	_client().set(_UNSCORED_BACKFILL_PAUSE_KEY, reason)


def resume_unscored_backfill() -> None:
	_client().delete(_UNSCORED_BACKFILL_PAUSE_KEY)
