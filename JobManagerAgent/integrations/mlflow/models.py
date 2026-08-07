"""Durable (Postgres) storage for the 'production' prompt alias's change history -- see
docs/backfill-design.md's durability section. Same reasoning as backfill/models.py: this is an
audit trail (when did production change, from what, to what, why), not fast ephemeral state.
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.job_data import Base
from utils.config import DEFAULT_PROMPT_ACTIVE_HISTORY_TABLE_NAME


def load_prompt_active_history_table_name() -> str:
	name = os.getenv("PROMPT_ACTIVE_HISTORY_TABLE_NAME", DEFAULT_PROMPT_ACTIVE_HISTORY_TABLE_NAME).strip()
	return name or DEFAULT_PROMPT_ACTIVE_HISTORY_TABLE_NAME


class PromptActiveHistoryRecord(Base):
	__tablename__ = load_prompt_active_history_table_name()

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
	from_version: Mapped[str | None] = mapped_column(String(50))
	to_version: Mapped[str] = mapped_column(String(50), nullable=False)
	schema_mode: Mapped[str] = mapped_column(String(20), nullable=False)
	rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)
	reason: Mapped[str] = mapped_column(String(255), nullable=False)
