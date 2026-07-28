from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from evals.dataset import DatasetError
from evals.run_offline_eval import run_offline_eval
from integrations.streaming.stream_events import utc_now_iso
from utils.agent_logger import get_agent_logger, new_id
from utils.config import PROJECT_ROOT


LOGGER = get_agent_logger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])

# dataset paths from client requests are only ever allowed to resolve inside here -- otherwise
# an absolute path or a `..`-laden relative one would let a caller point run_offline_eval() at
# any file readable by this process (e.g. `.env`), not just golden-dataset JSONL files.
_EVALS_DIR = (PROJECT_ROOT / "evals").resolve()


class EvalTriggerRequest(BaseModel):
	dataset: str = "evals/golden_dataset.jsonl"
	prompt_source: Literal["production", "local"] = "production"
	provider: str | None = None
	model: str | None = None
	threshold: int | None = None
	experiment_name: str | None = None
	run_name: str | None = None
	limit: int | None = None


class EvalTriggerResponse(BaseModel):
	eval_id: str
	status: Literal["running"]


class EvalStatusResponse(BaseModel):
	eval_id: str
	status: Literal["running", "completed", "failed"]
	started_at: str
	finished_at: str | None
	request: EvalTriggerRequest
	result: dict[str, Any] | None = None
	error: str | None = None


@dataclass
class _EvalRunRecord:
	eval_id: str
	status: Literal["running", "completed", "failed"]
	started_at: str
	request: EvalTriggerRequest
	finished_at: str | None = None
	result: dict[str, Any] | None = None
	error: str | None = None


# In-memory only -- eval runs are a manual/dev workflow triggered ad hoc, not something that needs
# to survive a restart; the durable record of a run is the MLflow run it logs to (find it by
# run_name, which defaults to this same eval_id -- see trigger_eval below).
_RUNS: dict[str, _EvalRunRecord] = {}
_RUNS_LOCK = threading.Lock()


def _resolve_dataset_path(raw: str) -> Path:
	candidate = Path(raw)
	if candidate.is_absolute():
		raise HTTPException(status_code=400, detail="dataset must be a relative path under evals/")
	resolved = (PROJECT_ROOT / candidate).resolve()
	if not resolved.is_relative_to(_EVALS_DIR):
		raise HTTPException(status_code=400, detail="dataset must resolve to a path under evals/")
	return resolved


def _mark_failed(eval_id: str, message: str) -> None:
	with _RUNS_LOCK:
		record = _RUNS[eval_id]
		record.status = "failed"
		record.error = message
		record.finished_at = utc_now_iso()


def _run_eval_in_background(eval_id: str, dataset_path: Path, payload: EvalTriggerRequest, run_name: str) -> None:
	log = LOGGER.bind(eval_id=eval_id)
	log.action("api_eval_started", dataset=str(dataset_path))
	try:
		summary = run_offline_eval(
			dataset_path=dataset_path,
			prompt_source=payload.prompt_source,
			provider=payload.provider,
			model=payload.model,
			threshold=payload.threshold,
			experiment_name=payload.experiment_name,
			run_name=run_name,
			limit=payload.limit,
		)
	except DatasetError as error:
		_mark_failed(eval_id, f"Invalid golden dataset: {error}")
		log.action("api_eval_failed", error=str(error))
		return
	except Exception as error:
		log.exception("Eval run failed")
		_mark_failed(eval_id, str(error))
		return

	with _RUNS_LOCK:
		record = _RUNS[eval_id]
		record.status = "completed"
		record.result = summary
		record.finished_at = utc_now_iso()
	log.action("api_eval_completed", **summary)


def _to_status_response(record: _EvalRunRecord) -> EvalStatusResponse:
	return EvalStatusResponse(
		eval_id=record.eval_id,
		status=record.status,
		started_at=record.started_at,
		finished_at=record.finished_at,
		request=record.request,
		result=record.result,
		error=record.error,
	)


@router.post("", status_code=202)
def trigger_eval(payload: EvalTriggerRequest) -> EvalTriggerResponse:
	"""Kicks off evals/run_offline_eval.py's run_offline_eval() on a background thread and
	returns immediately -- a full run against the real golden dataset can take 10+ minutes under
	the default RPM cap, far longer than is reasonable to hold an HTTP request open for. Poll
	GET /evals/{eval_id} for status/result. Concurrent triggers are not serialized against each
	other; they share the same Redis-backed RPM budget as everything else (rate_limiter.py), and
	each gets its own MLflow run via a distinct run_name, so running more than one at once is
	safe, just slower per-run.
	"""
	dataset_path = _resolve_dataset_path(payload.dataset)
	if not dataset_path.exists():
		raise HTTPException(status_code=400, detail=f"Dataset not found: {dataset_path}")

	eval_id = new_id()
	run_name = payload.run_name or eval_id
	record = _EvalRunRecord(
		eval_id=eval_id,
		status="running",
		started_at=utc_now_iso(),
		request=payload,
	)
	with _RUNS_LOCK:
		_RUNS[eval_id] = record

	thread = threading.Thread(
		target=_run_eval_in_background,
		args=(eval_id, dataset_path, payload, run_name),
		daemon=True,
		name=f"eval-{eval_id}",
	)
	thread.start()
	return EvalTriggerResponse(eval_id=eval_id, status="running")


@router.get("/{eval_id}")
def get_eval(eval_id: str) -> EvalStatusResponse:
	with _RUNS_LOCK:
		record = _RUNS.get(eval_id)
	if record is None:
		raise HTTPException(status_code=404, detail=f"No eval run with id {eval_id!r}")
	return _to_status_response(record)


@router.get("")
def list_evals() -> list[EvalStatusResponse]:
	with _RUNS_LOCK:
		records = list(_RUNS.values())
	return [_to_status_response(record) for record in records]
