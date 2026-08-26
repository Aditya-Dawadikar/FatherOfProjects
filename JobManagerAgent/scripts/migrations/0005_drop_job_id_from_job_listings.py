"""Contract migration: drop job_listings.job_id and promote the surrogate `id` (added nullable-
alongside in 0003) to the real primary key.

This is the step 0003's docstring described as gated on every consuming service being redeployed
onto id/source_job_id/source-based code first -- WebScraper, JobDataServer, and JobManagerAgent are
all being redeployed together with this migration (see their shared/job_data.py, dataWriter.py,
main.py, tools/db_tools.py, agent_tools.py changes landing in the same change), so it's safe to run
now rather than waiting for a separate bake-in window.

Ashby and Lever job ids are UUID strings and Greenhouse ids, while numeric, come from a separate id
space than YC's -- none of that can be inserted into an INTEGER PRIMARY KEY column, so this is also
the migration that actually unblocks writing rows for those sources at all.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from shared.job_data import load_job_table_name


def apply(conn: Connection) -> None:
	table_name = load_job_table_name()

	has_job_id = conn.execute(
		text(
			"""
			SELECT 1 FROM information_schema.columns
			WHERE table_name = :table_name AND column_name = 'job_id'
			"""
		),
		{"table_name": table_name},
	).first()
	if has_job_id is None:
		print(f"{table_name!r}.job_id already dropped; skipping.")
		return

	unresolved = conn.execute(
		text(f'SELECT count(*) FROM "{table_name}" WHERE source_job_id IS NULL OR source IS NULL')
	).scalar_one()
	if unresolved:
		raise RuntimeError(
			f"{unresolved} row(s) in {table_name!r} have NULL source_job_id/source; refusing to drop "
			f"job_id until every row has been backfilled (see 0003_add_source_and_surrogate_key_to_job_listings.py)."
		)

	print(f"Setting source_job_id/source NOT NULL on {table_name!r}")
	conn.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN source_job_id SET NOT NULL'))
	conn.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN source SET NOT NULL'))

	print(f"Dropping job_id's primary key and promoting id to primary key on {table_name!r}")
	conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{table_name}_pkey"'))
	conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY (id)'))

	print(f"Dropping legacy job_id column from {table_name!r}")
	conn.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN job_id'))
