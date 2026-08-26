"""Contract migration: drop job_matches.job_id and repoint its primary key to
(job_listing_id, prompt_version).

Companion to 0005_drop_job_id_from_job_listings.py, run in the same deploy -- JobManagerAgent (the
sole writer, via tools/db_tools.py's record_job_result) and JobDataServer (the reader, via
main.py's joins) are both being redeployed onto job_listing_id-based code at the same time, so
there's no bake-in window to wait for here either.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from shared.job_match_data import load_job_match_table_name


def apply(conn: Connection) -> None:
	table_name = load_job_match_table_name()

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

	unresolved = conn.execute(text(f'SELECT count(*) FROM "{table_name}" WHERE job_listing_id IS NULL')).scalar_one()
	if unresolved:
		raise RuntimeError(
			f"{unresolved} row(s) in {table_name!r} have NULL job_listing_id; refusing to drop job_id "
			f"until every row has been backfilled (see 0004_add_job_listing_id_to_job_matches.py)."
		)

	print(f"Setting job_listing_id NOT NULL on {table_name!r}")
	conn.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN job_listing_id SET NOT NULL'))

	print(f"Dropping the (job_id, prompt_version) primary key and adding (job_listing_id, prompt_version) on {table_name!r}")
	conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{table_name}_pkey"'))
	conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY (job_listing_id, prompt_version)'))

	print(f"Dropping legacy job_id column from {table_name!r}")
	conn.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN job_id'))
