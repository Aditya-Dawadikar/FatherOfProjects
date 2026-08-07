"""One-time migration: widen job_matches' primary key from job_id alone to
(job_id, prompt_version), and add the score_breakdown column used by rubric-based
prompts (job_match_v4/v5+).

Why this can't just be `Base.metadata.create_all(engine)`: that call only creates
tables that don't exist yet, it never alters an existing table's columns or
constraints (see shared/job_data.py, shared/job_match_data.py -- both are plain
declarative models with no migration framework backing them, by design, since this
repo has no Alembic). Widening the PK is a real ALTER TABLE, so it needs to run once,
by hand, against the shared Postgres instance before deploying the code that assumes
the new shape.

Safe to re-run: every step is guarded by a catalog check, so a second run is a no-op.

Usage: python -m scripts.migrate_job_matches_v2
"""

from __future__ import annotations

from sqlalchemy import text

from shared.job_data import create_db_engine, load_database_url
from shared.job_match_data import load_job_match_table_name


def migrate() -> None:
    table_name = load_job_match_table_name()
    engine = create_db_engine(load_database_url())

    with engine.begin() as conn:
        pk_constraint = conn.execute(
            text(
                """
                SELECT tc.constraint_name, array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                WHERE tc.table_name = :table_name
                  AND tc.constraint_type = 'PRIMARY KEY'
                GROUP BY tc.constraint_name
                """
            ),
            {"table_name": table_name},
        ).first()

        if pk_constraint is None:
            print(f"No existing primary key found on {table_name!r}; nothing to drop.")
        elif list(pk_constraint.columns) == ["job_id", "prompt_version"]:
            print(f"{table_name!r} already has the composite (job_id, prompt_version) primary key; skipping.")
        else:
            print(f"Dropping primary key {pk_constraint.constraint_name!r} on {table_name!r} (columns={pk_constraint.columns})")
            conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{pk_constraint.constraint_name}"'))
            print(f"Adding composite primary key (job_id, prompt_version) on {table_name!r}")
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY (job_id, prompt_version)'))

        column_exists = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = :table_name AND column_name = 'score_breakdown'
                """
            ),
            {"table_name": table_name},
        ).first()

        if column_exists is None:
            print(f"Adding score_breakdown JSONB column to {table_name!r}")
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN score_breakdown JSONB'))
        else:
            print(f"{table_name!r}.score_breakdown already exists; skipping.")

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
