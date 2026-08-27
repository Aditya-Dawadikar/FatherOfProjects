"""Generic named on/off switch registry -- see JobManagerAgent/scripts/migrations/
0007_add_feature_flags.py for why this exists instead of another bespoke Redis key + endpoint pair
per switch. JobManagerAgent owns the migration and the admin API for writing flags; this copy
(same duplication convention as shared/job_data.py) only needs to read them.

Adding a new flag: pick a name (a new module-level constant below), add a seed row in a
JobManagerAgent migration (optional -- is_enabled()'s `default` covers an unseeded flag), and call
is_enabled() at whatever gate point needs it here. No schema change.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Engine, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from shared.job_data import Base


# Every flag currently gating something in this service.
SCRAPE_ENABLED = "scrape_enabled"


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
	next check. Returns `default` if the row doesn't exist yet, so absence degrades to "on" rather
	than crashing or silently disabling something nobody meant to disable.
	"""
	with Session(engine) as session:
		row = session.get(FeatureFlag, name)
	return row.enabled if row is not None else default
