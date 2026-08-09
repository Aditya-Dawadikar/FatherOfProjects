"""Add job_matches.rubric_version and backfill it for rows written before the column existed.

Why this exists: job_matches.prompt_version is the raw MLflow-registered version id (e.g. "4",
"5"), and /matches/funnel filters/defaults on that exact string. job_match_v4.txt (schema_mode
"single", the live prompt) and job_match_v5.txt (schema_mode "batch", backfill-only) do the exact
same rubric-based scoring -- v5 only exists to amortize LLM calls across a batch -- and both carry
rubric_version=2 in their .meta.json sidecar (see integrations/mlflow/prompt_registry.py). But
because the two are different prompt_version strings, a backfill run under v5 produced rows the
live v4 funnel query could never see: once backfill outpaced live scoring, /matches/funnel's
"default to the most recently evaluated prompt_version" rule picked v5, and the alluvial chart
went empty because literally nothing had been scored under v4 by volume.

rubric_version is the column that actually answers "was this job scored by the same logic",
independent of schema_mode/batch size -- this migration adds it and backfills existing rows by
resolving each distinct prompt_version already in the table through MLflow (the same lookup
get_active_prompt/load_prompt_version already do), so historical rows written before this feature
landed are grouped correctly too, not just rows written after this deploy.

Requires MLflow to be reachable at startup to backfill existing rows; if a given prompt_version
can't be resolved (MLflow briefly down, or a stale/deleted version), that group is left NULL rather
than failing the whole migration -- /matches/funnel's rubric_version default query already skips
NULLs, so an unresolved legacy prompt_version just doesn't contribute to the grouped default
instead of crashing startup.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from integrations.mlflow.prompt_registry import load_prompt_version
from shared.job_match_data import load_job_match_table_name
from utils.agent_logger import get_agent_logger


LOGGER = get_agent_logger(__name__)


def apply(conn: Connection) -> None:
	table_name = load_job_match_table_name()

	column_exists = conn.execute(
		text(
			"""
			SELECT 1 FROM information_schema.columns
			WHERE table_name = :table_name AND column_name = 'rubric_version'
			"""
		),
		{"table_name": table_name},
	).first()

	if column_exists is None:
		print(f"Adding rubric_version INTEGER column to {table_name!r}")
		conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN rubric_version INTEGER'))
	else:
		print(f"{table_name!r}.rubric_version already exists; skipping column add.")

	unresolved_versions = conn.execute(
		text(f'SELECT DISTINCT prompt_version FROM "{table_name}" WHERE rubric_version IS NULL')
	).scalars().all()

	if not unresolved_versions:
		print(f"No {table_name!r} rows need rubric_version backfill.")
		return

	print(f"Backfilling rubric_version for {len(unresolved_versions)} distinct prompt_version(s): {unresolved_versions}")
	for prompt_version in unresolved_versions:
		try:
			rubric_version = load_prompt_version(prompt_version).rubric_version
		except Exception:
			# AgentLogger.exception is the plain logging.LoggerAdapter one (no **fields support like
			# .action has), so context goes in the message itself here.
			LOGGER.exception("rubric_version_backfill_lookup_failed prompt_version=%r", prompt_version)
			print(f"  prompt_version={prompt_version!r}: could not resolve via MLflow, leaving rubric_version NULL")
			continue

		result = conn.execute(
			text(
				f'UPDATE "{table_name}" SET rubric_version = :rubric_version '
				f"WHERE prompt_version = :prompt_version AND rubric_version IS NULL"
			),
			{"rubric_version": rubric_version, "prompt_version": prompt_version},
		)
		print(f"  prompt_version={prompt_version!r} -> rubric_version={rubric_version}: {result.rowcount} row(s) updated")
