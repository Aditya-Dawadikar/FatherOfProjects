from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.job_data import Base


DEFAULT_JOB_MATCH_TABLE_NAME = "job_matches"


def load_job_match_table_name() -> str:
	return os.getenv("JOB_MATCH_TABLE_NAME", DEFAULT_JOB_MATCH_TABLE_NAME).strip() or DEFAULT_JOB_MATCH_TABLE_NAME


class JobMatch(Base):
	"""Mirrors JobManagerAgent's shared/job_match_data.py -- JobManagerAgent is the only writer
	(tools/db_tools.py's record_job_result, run once per job right after its ReAct agent scores
	it against the resume), this service only reads the same `job_matches` table to serve query
	APIs over already-processed jobs. The two services don't share a package, so this column set
	has to be kept in sync with JobManagerAgent's model by hand if that schema ever changes.
	"""

	__tablename__ = load_job_match_table_name()

	# Composite PK (job_id, prompt_version): a job can carry one row per prompt version it's
	# been scored under (its original score plus any backfilled rubric score), not just one
	# ever. See JobManagerAgent/scripts/migrate_job_matches_v2.py for the one-time migration.
	job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
	prompt_version: Mapped[str] = mapped_column(String(50), primary_key=True)
	match_score: Mapped[int] = mapped_column(Integer, nullable=False)
	is_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
	reasoning: Mapped[str | None] = mapped_column(Text)
	prompt_name: Mapped[str] = mapped_column(String(255), nullable=False)
	model_name: Mapped[str] = mapped_column(String(255), nullable=False)
	evaluated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=False),
		default=datetime.utcnow,
		nullable=False,
	)
	# Raw per-criterion breakdown from a rubric-based prompt; NULL for legacy (v1-v3) rows.
	# See JobManagerAgent/llm_providers/base.py:compute_match_result for how match_score is
	# deterministically derived from this rather than being LLM-decided.
	score_breakdown: Mapped[dict | None] = mapped_column(JSON)
