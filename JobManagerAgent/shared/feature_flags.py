"""Generic named on/off switch registry -- see scripts/migrations/0007_add_feature_flags.py for
why this exists instead of another bespoke Redis key + endpoint pair per switch.

Adding a new flag: pick a name (a new module-level constant below, for discoverability/typo-safety
at call sites), add a seed row in a migration (optional -- is_enabled()'s `default` covers an
unseeded flag), and call is_enabled() at whatever gate point needs it. No schema change.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Engine, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from shared.job_data import Base


# Every flag currently gating something -- see the docstring above for adding another.
SCRAPE_ENABLED = "scrape_enabled"
AGENT_LIVE_ENABLED = "agent_live_enabled"
AGENT_BACKFILL_ENABLED = "agent_backfill_enabled"


class FeatureFlag(Base):
	__tablename__ = "feature_flags"

	name: Mapped[str] = mapped_column(Text, primary_key=True)
	enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
	description: Mapped[str | None] = mapped_column(Text)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=False),
		default=datetime.utcnow,
		onupdate=datetime.utcnow,
		nullable=False,
	)
	updated_reason: Mapped[str | None] = mapped_column(Text)


def is_enabled(engine: Engine, name: str, *, default: bool = True) -> bool:
	"""Reads fresh from Postgres on every call (no caching) so a flip takes effect on the very
	next check -- same "no caching" philosophy as the unscored-backfill pause flag this table
	folds in. Returns `default` if the row doesn't exist yet (an unseeded flag, or a service still
	on code from before this flag's migration landed), so absence degrades to "on" rather than
	crashing or silently disabling something nobody meant to disable.
	"""
	with Session(engine) as session:
		row = session.get(FeatureFlag, name)
	return row.enabled if row is not None else default


def set_flag(engine: Engine, name: str, enabled: bool, *, reason: str | None = None, description: str | None = None) -> FeatureFlag:
	"""Upserts -- works even for a flag not yet seeded by a migration, so a new flag's call site
	and dashboard toggle don't have to wait on a deploy/migration order."""
	with Session(engine) as session:
		row = session.get(FeatureFlag, name)
		if row is None:
			row = FeatureFlag(name=name, enabled=enabled, description=description, updated_reason=reason)
			session.add(row)
		else:
			row.enabled = enabled
			row.updated_reason = reason
			if description is not None:
				row.description = description
		session.commit()
		session.refresh(row)
		return row


def list_flags(engine: Engine) -> list[FeatureFlag]:
	with Session(engine) as session:
		return list(session.query(FeatureFlag).order_by(FeatureFlag.name).all())
