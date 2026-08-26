"""Add job_matches.job_listing_id, a FK to job_listings.id, ahead of eventually repointing
job_matches' primary key away from job_id (YC's native integer id) once every consuming service has
cut over -- see 0003_add_source_and_surrogate_key_to_job_listings.py for why job_id can no longer be
a safe global key once Ashby/Greenhouse/Lever jobs exist, and for the expand -> dual-write ->
cutover -> contract sequence this migration is part of.

This migration only expands: job_id and the existing (job_id, prompt_version) primary key are left
completely untouched, and job_listing_id is added nullable, not NOT NULL -- JobManagerAgent (the
sole writer of job_matches) has to be redeployed before it can populate this column, and
JobDataServer's still-job_id-keyed reads keep working unmodified in the meantime.

Backfilling job_listing_id for every pre-existing row is expected to fully succeed here (unlike
0002's soft-skip-on-unresolved for rubric_version) because every row in this table predates
multi-source ingestion -- every one of them is a YC job, resolvable via job_listings.source_job_id/
source (populated by 0003). An unresolved row here is a real bug, not an expected gap, so this
migration raises rather than leaving it NULL.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from shared.job_data import DEFAULT_JOB_SOURCE, load_job_table_name
from shared.job_match_data import load_job_match_table_name


def apply(conn: Connection) -> None:
	table_name = load_job_match_table_name()
	job_table_name = load_job_table_name()

	column_exists = conn.execute(
		text(
			"""
			SELECT 1 FROM information_schema.columns
			WHERE table_name = :table_name AND column_name = 'job_listing_id'
			"""
		),
		{"table_name": table_name},
	).first()

	if column_exists is not None:
		print(f"{table_name!r}.job_listing_id already exists; skipping.")
		return

	print(f"Adding job_listing_id BIGINT column to {table_name!r} (nullable for now)")
	conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN job_listing_id BIGINT'))

	print(f"Backfilling job_listing_id from {job_table_name!r}.source_job_id/source")
	conn.execute(
		text(
			f'UPDATE "{table_name}" jm SET job_listing_id = jl.id '
			f'FROM "{job_table_name}" jl '
			f"WHERE jl.source_job_id = jm.job_id::text AND jl.source = :source "
			f"AND jm.job_listing_id IS NULL"
		),
		{"source": DEFAULT_JOB_SOURCE},
	)

	unresolved = conn.execute(text(f'SELECT count(*) FROM "{table_name}" WHERE job_listing_id IS NULL')).scalar_one()
	if unresolved:
		raise RuntimeError(
			f"{unresolved} row(s) in {table_name!r} could not be matched to a {job_table_name!r} row via "
			f"source_job_id/source; refusing to add the job_listing_id foreign key with unresolved rows."
		)

	print(f"Adding job_listing_id -> {job_table_name!r}.id foreign key on {table_name!r}")
	conn.execute(
		text(
			f'ALTER TABLE "{table_name}" ADD CONSTRAINT fk_job_matches_job_listing '
			f'FOREIGN KEY (job_listing_id) REFERENCES "{job_table_name}" (id)'
		)
	)
