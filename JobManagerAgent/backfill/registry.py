from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import Engine


@dataclass(frozen=True)
class BatchOutcome:
	"""What one call to a BackfillProcess's run_one_batch produced -- the engine (engine.py)
	folds these into a run's running totals rather than a process managing its own counters."""

	rescored: int = 0
	not_found_404: int = 0
	crawl_error: int = 0
	errored: int = 0


@dataclass(frozen=True)
class BackfillContext:
	"""Infrastructure every backfill process shares, built once per run by engine.py and handed
	to run_one_batch -- a process reads what it needs off this rather than re-resolving its own
	DB engine/LLM client.

	No rate limiter here: RPM enforcement lives entirely inside the scoring call itself
	(llm_providers.score_jobs_batch passes bucket="backfill" down to
	gemini_provider.py:_generate_content, the actual network-call choke point), so a process
	never needs to acquire anything explicitly -- see rescore_with_prompt.py's comment on why an
	extra caller-side acquire() would be redundant rather than protective.
	"""

	engine: Engine
	llm_client: Any
	model: str
	provider: str
	resume_text: str
	threshold: int


@dataclass(frozen=True)
class BackfillProcess:
	"""A pluggable, named backfill routine. engine.py owns everything generic -- background
	execution, batching, the reserved RPM bucket, progress tracking -- a process only supplies
	*what* to select and *how* to process one batch of it, so the next backfill (this won't be
	the last one) plugs into the same machinery instead of re-deriving it.

	- `prepare(**params) -> dict`, optional: runs once before selection/batching; its return
	  value is merged into `params` for every later call (e.g. resolving a prompt_version string
	  into a loaded MLflow prompt object once, not once per batch).
	- `select_candidates(session, *, limit, **params) -> list[Any]`: the full candidate set for
	  this run (paged into batches by the engine), most-important-first.
	- `run_one_batch(session, batch, *, context, **params) -> BatchOutcome`: does the actual
	  work for one batch and returns counts for the engine to accumulate.
	"""

	name: str
	description: str
	select_candidates: Callable[..., list[Any]]
	run_one_batch: Callable[..., BatchOutcome]
	prepare: Callable[..., dict[str, Any]] | None = None


BACKFILL_PROCESSES: dict[str, BackfillProcess] = {}


def register_process(process: BackfillProcess) -> None:
	BACKFILL_PROCESSES[process.name] = process
