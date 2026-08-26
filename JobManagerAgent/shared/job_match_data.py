from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, Select, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column

from shared.job_data import Base, JobListing, load_job_table_name
from utils.config import DEFAULT_JOB_MATCH_TABLE_NAME


def load_job_match_table_name() -> str:
	return os.getenv("JOB_MATCH_TABLE_NAME", DEFAULT_JOB_MATCH_TABLE_NAME).strip() or DEFAULT_JOB_MATCH_TABLE_NAME


class JobMatch(Base):
	__tablename__ = load_job_match_table_name()

	# Composite PK (job_listing_id, prompt_version) -- not job_listing_id alone -- so the same job
	# can carry one row per prompt version it's been scored under (e.g. its original v1 score and a
	# rubric-based v4/v5 backfill score can coexist) instead of a re-score overwriting/colliding
	# with history. job_listing_id (FK to job_listings.id, the surrogate key -- see
	# scripts/migrations/0003_.../0004_.../0006_drop_job_id_from_job_matches.py) replaced the old
	# job_id INTEGER column once Ashby/Greenhouse/Lever jobs meant job_id alone could no longer
	# stay a safe global key.
	job_listing_id: Mapped[int] = mapped_column(BigInteger, ForeignKey(f"{load_job_table_name()}.id"), primary_key=True)
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
	# Raw per-criterion breakdown from a rubric-based prompt (schema_mode "single"/"batch"):
	# {"skills_match": {"score": 0-10, "reasoning": "..."}, ...}. NULL for legacy (v1-v3)
	# results, whose match_score/reasoning were decided by the LLM directly rather than
	# aggregated deterministically from criteria -- see llm_providers/base.py:compute_match_result.
	score_breakdown: Mapped[dict | None] = mapped_column(JSON)
	# The scoring logic identity, independent of prompt_version/schema_mode -- see
	# integrations/mlflow/prompt_registry.py's LoadedPrompt.rubric_version, resolved off each
	# prompts/job_match_v*.meta.json sidecar. v4 (schema_mode="single", live) and v5
	# (schema_mode="batch", backfill-only) are different prompt_version strings but the same
	# rubric_version, since batching is a throughput knob, not a scoring change -- this is what
	# lets JobDataServer's /matches/funnel group them into one population instead of the alluvial
	# chart going empty just because the live prompt's own exact prompt_version has no rows yet.
	# Nullable because rows written before this column existed have it backfilled by
	# scripts/migrations/0002_add_rubric_version_to_job_matches.py rather than at insert time.
	rubric_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


def unevaluated_job_ids_stmt(limit: int) -> Select:
	return (
		select(
			JobListing.id, JobListing.source, JobListing.source_job_id, JobListing.job_url,
			JobListing.job_role, JobListing.company_name,
		)
		.where(JobListing.id.notin_(select(JobMatch.job_listing_id)))
		.order_by(JobListing.updated_at.desc())
		.limit(limit)
	)


def reprocess_candidates_stmt(*, target_prompt_version: str, limit: int) -> Select:
	"""Jobs that have at least one job_matches row (under any prompt_version) but none yet
	under `target_prompt_version` -- the backfill candidate set for re-scoring already-matched
	jobs under a new prompt, as opposed to unevaluated_job_ids_stmt's "never scored at all"
	set. Ordered is_match DESC (a job counts as "matched" for priority purposes if ANY of its
	existing prompt-version rows say so, per the agreed backfill priority: match=true jobs
	first, then non-matches) then oldest-first-evaluated within each group, so a repeated/resumed
	backfill run always makes forward progress instead of re-picking recently-touched rows.

	Aggregates per job_listing_id (bool_or/min) rather than joining JobMatch directly onto
	JobListing -- a job can now have multiple job_matches rows (one per prompt_version), and a
	plain join would fan out into one duplicate JobListing row per existing version instead of one
	candidate per job.
	"""
	already_has_target_version = select(JobMatch.job_listing_id).where(JobMatch.prompt_version == target_prompt_version)
	existing_match_summary = (
		select(
			JobMatch.job_listing_id.label("job_listing_id"),
			func.bool_or(JobMatch.is_match).label("ever_matched"),
			func.min(JobMatch.evaluated_at).label("first_evaluated_at"),
		)
		.group_by(JobMatch.job_listing_id)
		.subquery()
	)
	return (
		select(
			JobListing.id, JobListing.source, JobListing.source_job_id, JobListing.job_url,
			JobListing.job_role, JobListing.company_name,
		)
		.join(existing_match_summary, existing_match_summary.c.job_listing_id == JobListing.id)
		.where(JobListing.id.notin_(already_has_target_version))
		.order_by(existing_match_summary.c.ever_matched.desc(), existing_match_summary.c.first_evaluated_at.asc())
		.limit(limit)
	)
