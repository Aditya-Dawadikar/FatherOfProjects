"""Adds the feature_flags table: a generic, named on/off switch registry, replacing the pattern of
building a bespoke Redis key + endpoint pair every time something new needs a kill switch (see
utils/matching_controls.py's unscored-backfill pause, which this migration also folds in).

Backed by Postgres, not Redis, deliberately -- these are kill switches over real spend (scraping,
LLM calls), and losing that state to a Redis restart/eviction and silently reverting to "on" is a
real risk. Postgres already has the durable/audited-state precedent here (schema_migrations,
backfill_runs, prompt_active_history).

Seeded all `enabled = true` so applying this migration changes nothing about current behavior --
scrape_enabled/agent_live_enabled/agent_backfill_enabled only take effect once an operator
explicitly flips one via POST /admin/feature-flags/{name}. A flag added later needs no schema
change: just a new row (seeded here or inserted on first POST) and a new is_enabled() check at
whatever gate point needs it -- see shared/feature_flags.py.
"""

from __future__ import annotations

from sqlalchemy import Connection, text


_TABLE = "feature_flags"

_SEED_FLAGS = (
	("scrape_enabled", "WebScraper's whole pipeline run (scrape + write + purge) is skipped entirely when off."),
	("agent_live_enabled", "Live matching cycles (triggered by fresh scrapes) are skipped when off."),
	("agent_backfill_enabled", "Never-scored-jobs backfill cycles (idle-triggered) are skipped when off -- same switch POST /admin/unscored-backfill/pause and /resume now flip."),
)


def apply(conn: Connection) -> None:
	table_exists = conn.execute(
		text("SELECT 1 FROM information_schema.tables WHERE table_name = :table_name"),
		{"table_name": _TABLE},
	).first()

	if table_exists is None:
		print(f"Creating {_TABLE!r} table")
		conn.execute(
			text(
				f'CREATE TABLE "{_TABLE}" ('
				f"name TEXT PRIMARY KEY, "
				f"enabled BOOLEAN NOT NULL, "
				f"description TEXT, "
				f"updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(), "
				f"updated_reason TEXT"
				f")"
			)
		)
	else:
		print(f"{_TABLE!r} already exists; skipping create.")

	for name, description in _SEED_FLAGS:
		existing = conn.execute(
			text(f'SELECT 1 FROM "{_TABLE}" WHERE name = :name'), {"name": name}
		).first()
		if existing is not None:
			print(f"{_TABLE}.{name} already seeded; skipping.")
			continue
		print(f"Seeding {_TABLE}.{name} = enabled")
		# updated_at is set explicitly (not left to a column default) because this table may
		# already have been created by shared/feature_flags.py's ORM model via
		# Base.metadata.create_all() (called by get_shared_engine() before any migration runs) --
		# that path has no server-side DEFAULT on updated_at, only the ORM-side one, which a raw
		# INSERT here doesn't go through.
		conn.execute(
			text(
				f'INSERT INTO "{_TABLE}" (name, enabled, description, updated_at, updated_reason) '
				f"VALUES (:name, TRUE, :description, now(), 'seeded_by_migration')"
			),
			{"name": name, "description": description},
		)
