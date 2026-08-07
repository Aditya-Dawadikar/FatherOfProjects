from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backfill import BACKFILL_PROCESSES, get_run_status, list_run_statuses, request_cancel, start_backfill_run
from shared.job_data import get_shared_engine


router = APIRouter(prefix="/backfill", tags=["backfill"])


class BackfillProcessSummary(BaseModel):
	name: str
	description: str


@router.get("/processes", summary="List registered backfill processes")
def list_processes() -> list[BackfillProcessSummary]:
	"""Every process here can be triggered via POST /backfill/run -- this repo ships one
	(`rescore_with_prompt`, re-scores already-matched jobs under a new prompt version), and
	future backfill routines register into the same framework (see backfill/registry.py)
	instead of getting a bespoke endpoint each.
	"""
	return [
		BackfillProcessSummary(name=process.name, description=process.description)
		for process in BACKFILL_PROCESSES.values()
	]


class BackfillRunRequest(BaseModel):
	process: str = Field(..., description="A process name from GET /backfill/processes, e.g. 'rescore_with_prompt'.")
	params: dict[str, Any] = Field(
		default_factory=dict,
		description="Process-specific parameters, e.g. {'prompt_version': '5'} for rescore_with_prompt.",
	)
	limit: int | None = Field(
		default=None,
		description="Cap on candidates processed this run. Recommended: start with a small limit "
		"(e.g. 5-10) to validate output quality via the Matches page's detail card before "
		"re-triggering without a limit to process the full remaining candidate set -- rows written "
		"by the small run are real (not a dry-run/simulation) and are automatically excluded from "
		"the candidate set of a later run for the same prompt_version (see "
		"reprocess_candidates_stmt), so the two runs don't overlap or double-process anything.",
	)


class BackfillRunTriggerResponse(BaseModel):
	run_id: str
	status: Literal["running"]


@router.post("/run", status_code=202, summary="Trigger a backfill run")
def trigger_backfill(payload: BackfillRunRequest) -> BackfillRunTriggerResponse:
	"""Dev-facing endpoint (no auth, not meant to be exposed beyond internal/dev use) that starts
	the named process on a background thread and returns immediately -- a real backfill run
	against a large candidate set can take a long time under the reserved backfill RPM budget
	(deliberately small, see utils/config.py:BACKFILL_RPM_CAP, so it never crowds out live
	scoring). Poll GET /backfill/runs/{run_id} for progress/result.

	Pass `limit` to test on a small subset before committing to the full job -- see its field
	description for exactly how a small run and a later full run compose safely.

	Only one backfill run is ever allowed to be "running" at a time: triggering this while
	another run is still in flight automatically requests its cancellation first (cooperative --
	it finishes its current batch, then stops; nothing already written is purged). This is what
	keeps the reserved "backfill" RPM allocation a single, cleanly reassignable slice -- see
	docs/backfill-design.md's budget model -- and it never touches live or eval traffic to do it.
	"""
	if payload.process not in BACKFILL_PROCESSES:
		raise HTTPException(status_code=400, detail=f"Unknown process {payload.process!r}; see GET /backfill/processes")
	try:
		run_id = start_backfill_run(
			process_name=payload.process, params=payload.params, engine=get_shared_engine(), limit=payload.limit
		)
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error
	return BackfillRunTriggerResponse(run_id=run_id, status="running")


class BackfillRunStatusResponse(BaseModel):
	run_id: str
	process: str
	params: dict[str, Any]
	status: Literal["running", "completed", "failed", "cancelled"]
	candidate_count: int | None
	processed: int
	rescored: int
	not_found_404: int
	crawl_error: int
	errored: int
	error: str | None
	cancel_reason: str | None
	started_at: str
	finished_at: str | None


def _to_status_response(status: Any) -> BackfillRunStatusResponse:
	return BackfillRunStatusResponse(
		run_id=status.run_id,
		process=status.process_name,
		params=status.params,
		status=status.status,
		candidate_count=status.candidate_count,
		processed=status.processed,
		rescored=status.rescored,
		not_found_404=status.not_found_404,
		crawl_error=status.crawl_error,
		errored=status.errored,
		error=status.error_message,
		cancel_reason=status.cancel_reason,
		started_at=status.started_at.isoformat(),
		finished_at=status.finished_at.isoformat() if status.finished_at else None,
	)


@router.get("/runs/{run_id}", summary="Poll a backfill run's progress/status")
def get_backfill_run(run_id: str) -> BackfillRunStatusResponse:
	status = get_run_status(get_shared_engine(), run_id)
	if status is None:
		raise HTTPException(status_code=404, detail=f"No backfill run with id {run_id!r}")
	return _to_status_response(status)


@router.post("/runs/{run_id}/cancel", summary="Request cancellation of a running backfill run")
def cancel_backfill_run(run_id: str) -> BackfillRunStatusResponse:
	"""Cooperative cancel: the run stops after its current in-flight batch finishes (never
	mid-batch), and whatever it already wrote stays written -- no purge, matching the same
	revert-without-purge assumption promoting/reverting the active prompt relies on. Poll
	GET /backfill/runs/{run_id} to watch `status` become "cancelled". A no-op (200, unchanged) if
	the run has already finished on its own.
	"""
	engine = get_shared_engine()
	status = get_run_status(engine, run_id)
	if status is None:
		raise HTTPException(status_code=404, detail=f"No backfill run with id {run_id!r}")
	if status.status == "running":
		request_cancel(engine, run_id, reason="manual_cancel")
	return _to_status_response(status)


@router.get("/runs", summary="List recent backfill runs (most recent first)")
def list_backfill_runs(limit: int = 50) -> list[BackfillRunStatusResponse]:
	"""The durable "historical backfill log" -- when was the last backfill triggered, with what
	params, and how did it end (completed/failed/cancelled/superseded) -- survives redeploys since
	run history is Postgres-backed (see backfill/models.py), not in-process memory or Redis.
	"""
	return [_to_status_response(status) for status in list_run_statuses(get_shared_engine(), limit=limit)]
