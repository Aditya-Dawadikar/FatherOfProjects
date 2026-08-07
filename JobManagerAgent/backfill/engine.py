from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from llm_providers import build_client, load_provider_name
from utils.agent_logger import get_agent_logger, new_id
from utils.config import DEFAULT_MODEL, load_backfill_batch_size, load_match_threshold, load_resume

from .models import BackfillRunRecord
from .registry import BACKFILL_PROCESSES, BackfillContext


LOGGER = get_agent_logger(__name__)


@dataclass
class BackfillRunStatus:
	run_id: str
	process_name: str
	params: dict[str, Any]
	status: str = "running"  # running | completed | failed | cancelled
	candidate_count: int | None = None
	processed: int = 0
	rescored: int = 0
	not_found_404: int = 0
	crawl_error: int = 0
	errored: int = 0
	error_message: str | None = None
	cancel_reason: str | None = None
	started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
	finished_at: datetime | None = None


def _row_to_status(row: BackfillRunRecord) -> BackfillRunStatus:
	return BackfillRunStatus(
		run_id=row.run_id,
		process_name=row.process_name,
		params=row.params,
		status=row.status,
		candidate_count=row.candidate_count,
		processed=row.processed,
		rescored=row.rescored,
		not_found_404=row.not_found_404,
		crawl_error=row.crawl_error,
		errored=row.errored,
		error_message=row.error_message,
		cancel_reason=row.cancel_reason,
		started_at=row.started_at,
		finished_at=row.finished_at,
	)


def _save_status(engine: Engine, status: BackfillRunStatus) -> None:
	"""Upsert -- durable (Postgres), not Redis/in-memory: a backfill run can span many minutes to
	hours, and this process redeploys on every push (Railway restarts the container). Called
	after every meaningful state change (candidate selection, each batch, completion), so
	GET /backfill/runs/{run_id} always reflects live progress, not just the final outcome.
	"""
	with Session(engine) as session:
		row = session.get(BackfillRunRecord, status.run_id)
		if row is None:
			row = BackfillRunRecord(run_id=status.run_id)
			session.add(row)
		row.process_name = status.process_name
		row.params = status.params
		row.status = status.status
		row.candidate_count = status.candidate_count
		row.processed = status.processed
		row.rescored = status.rescored
		row.not_found_404 = status.not_found_404
		row.crawl_error = status.crawl_error
		row.errored = status.errored
		row.error_message = status.error_message
		row.cancel_reason = status.cancel_reason
		row.started_at = status.started_at
		row.finished_at = status.finished_at
		session.commit()


def get_run_status(engine: Engine, run_id: str) -> BackfillRunStatus | None:
	with Session(engine) as session:
		row = session.get(BackfillRunRecord, run_id)
	return _row_to_status(row) if row is not None else None


def list_run_statuses(engine: Engine, limit: int = 50) -> list[BackfillRunStatus]:
	"""Most recent runs first -- the durable "historical backfill log" (when was the last
	backfill triggered, with what params, and how did it end) that GET /backfill/runs and the
	dashboard's migration observability page read from.
	"""
	with Session(engine) as session:
		rows = session.scalars(
			select(BackfillRunRecord).order_by(BackfillRunRecord.started_at.desc()).limit(limit)
		).all()
	return [_row_to_status(row) for row in rows]


def list_running_run_ids(engine: Engine) -> list[str]:
	with Session(engine) as session:
		return list(session.scalars(select(BackfillRunRecord.run_id).where(BackfillRunRecord.status == "running")))


def request_cancel(engine: Engine, run_id: str, *, reason: str) -> None:
	"""Sets `cancel_reason` while the run is (as far as this write knows) still "running" -- the
	run's own loop (see _execute) re-reads this column between batches and, once it sees it,
	flips status to "cancelled" using the same value. One column serves both "requested" and
	"recorded" for exactly that reason: by the time a run actually stops, they're always equal.
	"""
	with Session(engine) as session:
		row = session.get(BackfillRunRecord, run_id)
		if row is not None:
			row.cancel_reason = reason
			session.commit()


def _cancel_requested_reason(engine: Engine, run_id: str) -> str | None:
	with Session(engine) as session:
		row = session.get(BackfillRunRecord, run_id)
	return row.cancel_reason if row is not None else None


def _chunk(items: list[Any], size: int) -> list[list[Any]]:
	return [items[i : i + size] for i in range(0, len(items), size)]


def _execute(run_id: str, *, process_name: str, params: dict[str, Any], engine: Engine, limit: int | None) -> None:
	# Status row already exists (start_backfill_run wrote it synchronously before starting this
	# thread, so GET /backfill/runs/{run_id} can never 404 in the brief window between triggering
	# and this thread's first real progress update) -- re-fetch rather than recreate, in case
	# anything else (there isn't, today) touched it between then and now.
	status = get_run_status(engine, run_id) or BackfillRunStatus(run_id=run_id, process_name=process_name, params=params)
	log = LOGGER.bind(run_id=run_id, process=process_name)
	process = BACKFILL_PROCESSES[process_name]

	try:
		provider = load_provider_name()
		context = BackfillContext(
			engine=engine,
			llm_client=build_client(provider),
			model=DEFAULT_MODEL,
			provider=provider,
			resume_text=load_resume(),
			threshold=load_match_threshold(),
		)

		resolved_params = dict(params)
		if process.prepare is not None:
			resolved_params.update(process.prepare(**params))

		with Session(engine) as session:
			candidates = process.select_candidates(session, limit=limit, **resolved_params)
		status.candidate_count = len(candidates)
		log.action("backfill_candidates_selected", candidate_count=len(candidates))
		_save_status(engine, status)

		batch_size = load_backfill_batch_size()
		cancelled = False
		for batch in _chunk(candidates, batch_size):
			# Checked between batches, not mid-batch -- a batch already in flight (an LLM call
			# already sent) always finishes; nothing is rolled back or purged. See
			# docs/backfill-design.md's revert-without-purge decision: whatever's already been
			# written under the target prompt_version stays written and correct regardless of
			# whether this run goes on to complete, get cancelled, or gets superseded.
			cancel_reason = _cancel_requested_reason(engine, run_id)
			if cancel_reason is not None:
				status.status = "cancelled"
				status.cancel_reason = cancel_reason
				log.action("backfill_run_cancelled", cancel_reason=cancel_reason, processed_so_far=status.processed)
				cancelled = True
				break

			with Session(engine) as session:
				outcome = process.run_one_batch(session, batch, context=context, **resolved_params)
			status.processed += len(batch)
			status.rescored += outcome.rescored
			status.not_found_404 += outcome.not_found_404
			status.crawl_error += outcome.crawl_error
			status.errored += outcome.errored
			log.action(
				"backfill_batch_complete",
				batch_size=len(batch),
				processed_so_far=status.processed,
				rescored=outcome.rescored,
				not_found_404=outcome.not_found_404,
				crawl_error=outcome.crawl_error,
				errored=outcome.errored,
			)
			_save_status(engine, status)

		if not cancelled:
			status.status = "completed"
			log.action(
				"backfill_run_complete",
				processed=status.processed,
				rescored=status.rescored,
				not_found_404=status.not_found_404,
				crawl_error=status.crawl_error,
				errored=status.errored,
			)
	except Exception as error:
		# Runs on a background thread with no caller to propagate to -- GET /backfill/runs/{run_id}
		# is how this failure actually reaches anyone, so it's recorded on the status object
		# instead of re-raised into the void.
		log.action("backfill_run_failed", error=str(error))
		status.status = "failed"
		status.error_message = str(error)
	finally:
		status.finished_at = datetime.now(timezone.utc)
		_save_status(engine, status)


def start_backfill_run(*, process_name: str, params: dict[str, Any], engine: Engine, limit: int | None = None) -> str:
	"""Starts a registered BackfillProcess on a background thread and returns immediately with a
	run_id to poll (GET /backfill/runs/{run_id}) -- mirrors api/eval_runs.py's threading pattern
	for the same reason: a real backfill run can take far longer than is reasonable to hold an
	HTTP request open for.

	Enforces "only one backfill run at a time": any currently-"running" run is asked to cancel
	(cooperatively -- it finishes whatever batch is already in flight, then stops) before this
	one starts. This is what keeps the reserved "backfill" RPM allocation (see
	docs/backfill-design.md's x+y+z+w budget model) a single, cleanly reassignable slice that
	always belongs to exactly one process -- never split silently across two concurrent runs, and
	never requiring live/eval traffic to pause while the handoff happens.
	"""
	if process_name not in BACKFILL_PROCESSES:
		known = ", ".join(sorted(BACKFILL_PROCESSES)) or "(none registered)"
		raise ValueError(f"Unknown backfill process {process_name!r}; known processes: {known}")

	run_id = new_id()
	for running_run_id in list_running_run_ids(engine):
		request_cancel(engine, running_run_id, reason=f"superseded_by_run:{run_id}")
		LOGGER.action("backfill_run_superseded", superseded_run_id=running_run_id, new_run_id=run_id)

	_save_status(engine, BackfillRunStatus(run_id=run_id, process_name=process_name, params=params))

	thread = threading.Thread(
		target=_execute,
		kwargs={"run_id": run_id, "process_name": process_name, "params": params, "engine": engine, "limit": limit},
		daemon=True,
		name=f"backfill-{run_id}",
	)
	thread.start()
	return run_id
