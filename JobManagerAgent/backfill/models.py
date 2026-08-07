"""Durable (Postgres) storage for backfill run history -- see docs/backfill-design.md's
durability section. Redis was the first pass here and was wrong for this data: run history is an
audit trail that needs to survive a redeploy (this process restarts on every push), not fast
ephemeral state -- Postgres, already the durable store for job_matches, is the right home for it.
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.job_data import Base
from utils.config import DEFAULT_BACKFILL_RUNS_TABLE_NAME


def load_backfill_runs_table_name() -> str:
	return os.getenv("BACKFILL_RUNS_TABLE_NAME", DEFAULT_BACKFILL_RUNS_TABLE_NAME).strip() or DEFAULT_BACKFILL_RUNS_TABLE_NAME


class BackfillRunRecord(Base):
	__tablename__ = load_backfill_runs_table_name()

	run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
	process_name: Mapped[str] = mapped_column(String(255), nullable=False)
	params: Mapped[dict] = mapped_column(JSON, nullable=False)
	status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
	candidate_count: Mapped[int | None] = mapped_column(Integer)
	processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	rescored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	not_found_404: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	crawl_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	errored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	error_message: Mapped[str | None] = mapped_column(Text)
	# Doubles as both "cancellation requested" (set the moment supersession/manual-cancel fires,
	# while status is still "running") and "cancellation reason" (the same value, once the run's
	# own loop notices it between batches and flips status to "cancelled") -- one column instead
	# of two, since by construction they're always the same string once a run actually stops.
	cancel_reason: Mapped[str | None] = mapped_column(Text)
	started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
	finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
