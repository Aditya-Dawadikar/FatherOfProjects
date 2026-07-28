from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
	dataset: str = Field(
		default="evals/golden_dataset.jsonl",
		description="Path to a golden-dataset JSONL file, relative to evals/ (must resolve inside "
		"it -- absolute paths and `..` are rejected).",
	)
	prompt_source: Literal["production", "local"] = Field(
		default="production",
		description="'production' read-only-loads the MLflow-registered prompt at the "
		"'production' alias. 'local' scores prompts/job_match_v1.txt as it sits on disk right "
		"now, without registering/promoting it -- use this to validate an edit before the next "
		"live cycle auto-promotes it.",
	)
	provider: str | None = Field(default=None, description="Overrides LLM_PROVIDER for this run. Currently 'gemini' is the only accepted value.")
	model: str | None = Field(default=None, description="Overrides the active provider's model env var for this run.")
	threshold: int | None = Field(default=None, description="Overrides MATCH_THRESHOLD (0-100) for this run.")
	experiment_name: str | None = Field(default=None, description="Overrides MLFLOW_EVAL_EXPERIMENT_NAME for this run.")
	run_name: str | None = Field(default=None, description="MLflow run name; defaults to this trigger's eval_id.")
	limit: int | None = Field(
		default=None,
		description="Only score the first N cases. Recommended when testing via this page -- "
		"omitting it scores the entire dataset (60 cases in golden_dataset.jsonl), which makes "
		"that many real, billed Gemini calls and can take 10+ minutes under the default RPM cap.",
	)

	model_config = {
		"json_schema_extra": {
			"examples": [
				{"dataset": "evals/golden_dataset.example.jsonl", "prompt_source": "local", "limit": 1}
			]
		}
	}


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


@router.post("", status_code=202, summary="Trigger an offline eval run")
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


@router.get("/{eval_id}", summary="Poll an eval run's status/result")
def get_eval(eval_id: str) -> EvalStatusResponse:
	"""`status` is "running" until the background thread finishes. On "completed", `result` holds
	the same summary dict the CLI prints (accuracy/precision/recall/f1/...). On "failed", `error`
	holds the exception message -- check this first if a run seems stuck, since a bad dataset or
	an unreachable MLflow tracking server surfaces here rather than as an HTTP error (the trigger
	request already returned 202 by the time either of those would be discovered)."""
	with _RUNS_LOCK:
		record = _RUNS.get(eval_id)
	if record is None:
		raise HTTPException(status_code=404, detail=f"No eval run with id {eval_id!r}")
	return _to_status_response(record)


@router.get("", summary="List eval runs since this process started")
def list_evals() -> list[EvalStatusResponse]:
	"""In-memory only -- a server restart clears this list. Find older runs in the MLflow
	`job_matching_evals` experiment instead, by run_name (the eval_id, unless overridden)."""
	with _RUNS_LOCK:
		records = list(_RUNS.values())
	return [_to_status_response(record) for record in records]
