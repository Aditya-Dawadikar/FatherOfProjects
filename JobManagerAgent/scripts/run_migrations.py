"""Generic migration runner: applies every migration module under scripts/migrations/ that
hasn't been recorded in the schema_migrations tracking table yet, in filename order, each in its
own transaction.

This -- not hardcoding a specific migration by name at each call site -- is what makes adding a
migration a one-file change: drop a new 000N_description.py module in scripts/migrations/ with an
`apply(conn)` function, and both this runner and api/app.py's startup hook (which just calls
run_pending_migrations()) pick it up automatically. No call site needs to know which migration is
"latest".

Deliberately not Alembic (see scripts/migrations/0001_...py's docstring for why this repo doesn't
have a migration framework already) -- this is the smallest thing that gives the two properties
that actually matter here: migrations run in a defined order, and each one runs at most once.

Usage: python -m scripts.run_migrations
"""

from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Connection, Engine, text

from shared.job_data import get_shared_engine

from . import migrations as _migrations_package


_TRACKING_TABLE = "schema_migrations"


def _ensure_tracking_table(conn: Connection) -> None:
	conn.execute(
		text(
			f'CREATE TABLE IF NOT EXISTS "{_TRACKING_TABLE}" ('
			f"name TEXT PRIMARY KEY, applied_at TIMESTAMP WITHOUT TIME ZONE NOT NULL)"
		)
	)


def _applied_names(conn: Connection) -> set[str]:
	rows = conn.execute(text(f'SELECT name FROM "{_TRACKING_TABLE}"')).all()
	return {row[0] for row in rows}


def _discover_migrations() -> list[tuple[str, Any]]:
	# Sorted by module (file) name -- the 000N_ prefix is what makes that sort order also the
	# intended application order. importlib.import_module works fine with a leading-digit module
	# name (same trick Django's migration loader relies on) even though it's not valid bare
	# `import` syntax.
	return [
		(module_info.name, importlib.import_module(f"{_migrations_package.__name__}.{module_info.name}"))
		for module_info in sorted(pkgutil.iter_modules(_migrations_package.__path__), key=lambda m: m.name)
	]


def run_pending_migrations(engine: Engine | None = None) -> list[str]:
	"""Applies whichever migrations in scripts/migrations/ haven't been recorded as applied yet.
	Returns the names of the migrations actually applied this call (empty if the schema was
	already current). Safe to call on every process boot -- see api/app.py's lifespan.
	"""
	engine = engine or get_shared_engine()

	with engine.begin() as conn:
		_ensure_tracking_table(conn)
		already_applied = _applied_names(conn)

	applied_now: list[str] = []
	for name, module in _discover_migrations():
		if name in already_applied:
			continue
		with engine.begin() as conn:
			module.apply(conn)
			conn.execute(
				text(f'INSERT INTO "{_TRACKING_TABLE}" (name, applied_at) VALUES (:name, :applied_at)'),
				{"name": name, "applied_at": datetime.now(timezone.utc).replace(tzinfo=None)},
			)
		applied_now.append(name)

	return applied_now


if __name__ == "__main__":
	applied = run_pending_migrations()
	if applied:
		print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
	else:
		print("Schema already current; no pending migrations.")
