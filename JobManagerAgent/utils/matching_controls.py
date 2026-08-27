"""Operator control over the never-scored-jobs backfill (mode="backfill" cycles, triggered by
integrations/streaming/stream_consumer.py's idle timeout via api/agent_worker.py's on_idle) --
NOT the backfill/ package's rescore-under-a-new-prompt-version process, which is a separate,
explicitly-triggered mechanism (see docs/backfill-design.md for why the two are kept orthogonal).

This exists so a prompt cutover can be driven as a predictable sequence -- pause here, promote
the new prompt version (POST /admin/active-prompt), resume here -- rather than only relying on
get_active_prompt() re-resolving the 'production' alias fresh on every cycle. That re-resolution
alone is enough for correctness (see prompt_registry.py's docstring), but pausing gives an
operator a clean window with zero backfill-mode cycles in flight while the switch happens.

Thin wrapper over shared/feature_flags.py's agent_backfill_enabled flag (see
scripts/migrations/0007_add_feature_flags.py) -- this used to be its own bespoke Redis key; it's
the same on/off switch agents/react_agent.py checks for every mode="backfill" cycle now, just
exposed under this module's existing names so api/admin.py's endpoints didn't need to change.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.feature_flags import AGENT_BACKFILL_ENABLED, FeatureFlag, is_enabled, set_flag
from shared.job_data import get_shared_engine


def unscored_backfill_pause_reason() -> str | None:
	"""Returns the reason it was paused, or None if it's currently enabled -- mirrors the old
	Redis-key-presence check's return shape so callers don't need to change."""
	engine = get_shared_engine()
	if is_enabled(engine, AGENT_BACKFILL_ENABLED):
		return None
	with Session(engine) as session:
		row = session.get(FeatureFlag, AGENT_BACKFILL_ENABLED)
	return row.updated_reason if row is not None else "manual_pause"


def is_unscored_backfill_paused() -> bool:
	return unscored_backfill_pause_reason() is not None


def pause_unscored_backfill(*, reason: str) -> None:
	set_flag(get_shared_engine(), AGENT_BACKFILL_ENABLED, False, reason=reason)


def resume_unscored_backfill() -> None:
	set_flag(get_shared_engine(), AGENT_BACKFILL_ENABLED, True, reason=None)
