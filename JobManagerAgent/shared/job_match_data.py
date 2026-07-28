from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Select, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from shared.job_data import Base, JobListing
from utils.config import DEFAULT_JOB_MATCH_TABLE_NAME


def load_job_match_table_name() -> str:
	return os.getenv("JOB_MATCH_TABLE_NAME", DEFAULT_JOB_MATCH_TABLE_NAME).strip() or DEFAULT_JOB_MATCH_TABLE_NAME


class JobMatch(Base):
	__tablename__ = load_job_match_table_name()

	job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
	match_score: Mapped[int] = mapped_column(Integer, nullable=False)
	is_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
	reasoning: Mapped[str | None] = mapped_column(Text)
	prompt_name: Mapped[str] = mapped_column(String(255), nullable=False)
	prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
	model_name: Mapped[str] = mapped_column(String(255), nullable=False)
	evaluated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=False),
		default=datetime.utcnow,
		nullable=False,
	)


def unevaluated_job_ids_stmt(limit: int) -> Select:
	return (
		select(JobListing.job_id, JobListing.job_url, JobListing.job_role, JobListing.company_name)
		.where(JobListing.job_id.notin_(select(JobMatch.job_id)))
		.order_by(JobListing.updated_at.desc())
		.limit(limit)
	)
