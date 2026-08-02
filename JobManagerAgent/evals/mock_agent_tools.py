from __future__ import annotations

from typing import Any, Literal

import mlflow
from langchain_core.tools import tool

from .tool_eval_dataset import ToolEvalCase, ToolEvalJobCase


Phase = Literal["pending", "crawled", "evaluated", "recorded", "crawl_error", "eval_error"]
ErrorKind = Literal["scripted", "guardrail"] | None


def build_mock_agent_tools(
	case: ToolEvalCase,
) -> tuple[Any, Any, Any, Any, list[dict[str, Any]], dict[int, Phase]]:
	"""Stand-ins for tools/agent_tools.py's four tools, driven entirely by a ToolEvalCase's canned
	per-job data instead of a real DB/crawler/scoring model -- lets evals/run_tool_selection_eval.py
	invoke the real ReAct orchestrator (same system prompt, real LLM calls deciding tool order)
	against deterministic, curated scenarios without any live infrastructure.

	Each tool enforces the same dependency contract the real tools + system prompt describe (crawl
	before evaluate, evaluate before record, no double-crawl, no evaluating before a job list
	exists, ...) and returns an {"error": ...} dict on violation -- exactly like the real tools do
	for their own guardrails (unknown job_id, not-yet-crawled, ...). That means an agent that picks
	the wrong tool or the wrong order surfaces as a *guardrail* error here, distinct from a
	*scripted* error (a crawl/evaluate outcome the case deliberately set up to fail, e.g. a 404) --
	the caller uses that distinction to tell "the agent made a mistake" apart from "this scenario
	was supposed to error here."

	Returns `(get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool, calls, phases)`;
	`calls` is mutated in call order as the agent invokes tools, each entry
	`{"tool", "job_id", "is_error", "error_kind"}`; `phases` is mutated to reflect each job_id's
	final state (e.g. "recorded", "crawl_error") -- together these let the caller score the run
	without re-parsing the agent's message history.
	"""
	jobs_by_id: dict[int, ToolEvalJobCase] = {job.job_id: job for job in case.jobs}
	phases: dict[int, Phase] = {job.job_id: "pending" for job in case.jobs}
	batch_fetched = False

	calls: list[dict[str, Any]] = []

	def _record(tool_name: str, job_id: int | None, *, is_error: bool, error_kind: ErrorKind) -> None:
		calls.append({"tool": tool_name, "job_id": job_id, "is_error": is_error, "error_kind": error_kind})

	def _trace_tool_call(tool_name: str, tool_args: dict[str, Any], func: Any) -> Any:
		with mlflow.start_span(
			name=f"tool:{tool_name}",
			span_type="TOOL",
			attributes={"tool_name": tool_name, "tool_args": str(tool_args)},
		) as span:
			span.set_inputs({"args": tool_args})
			result = func()
			span.set_outputs({"result": result})
			return result

	@tool
	def get_jobs_to_process() -> list[dict[str, Any]]:
		"""Fetch the next batch of jobs that have not yet been evaluated. Each item has job_id,
		job_role, and company_name only -- call crawl_job(job_id) next for each one to get the
		full posting detail. Call this once at the start to get your work for this cycle; do not
		call it again afterward."""
		return _trace_tool_call("get_jobs_to_process", {}, _get_jobs_to_process_impl)

	def _get_jobs_to_process_impl() -> Any:
		nonlocal batch_fetched
		if batch_fetched:
			_record("get_jobs_to_process", None, is_error=True, error_kind="guardrail")
			return {"error": "get_jobs_to_process was already called this cycle; do not call it again"}
		batch_fetched = True
		_record("get_jobs_to_process", None, is_error=False, error_kind=None)
		return [{"job_id": job.job_id, "job_role": job.job_role, "company_name": job.company_name} for job in case.jobs]

	@tool
	def crawl_job(job_id: int) -> dict[str, Any]:
		"""Fetch the full posting detail for a job_id returned by get_jobs_to_process. Call this
		once per job_id, then call evaluate_match(job_id) next. If the result contains an "error"
		key, do not call evaluate_match for that job_id -- just move on to the next job."""
		return _trace_tool_call("crawl_job", {"job_id": job_id}, lambda: _crawl_job_impl(job_id))

	def _crawl_job_impl(job_id: int) -> dict[str, Any]:
		job = jobs_by_id.get(job_id)
		if job is None or not batch_fetched:
			_record("crawl_job", job_id, is_error=True, error_kind="guardrail")
			return {"error": f"unknown job_id={job_id}; call get_jobs_to_process first"}
		if phases[job_id] != "pending":
			_record("crawl_job", job_id, is_error=True, error_kind="guardrail")
			return {"error": f"job_id={job_id} has already been crawled; do not call crawl_job twice"}

		if job.crawl_error is not None:
			phases[job_id] = "crawl_error"
			_record("crawl_job", job_id, is_error=True, error_kind="scripted")
			return {"error": job.crawl_error}

		phases[job_id] = "crawled"
		_record("crawl_job", job_id, is_error=False, error_kind=None)
		assert job.crawl_result is not None
		return job.crawl_result

	@tool
	def evaluate_match(job_id: int) -> dict[str, Any]:
		"""Score a job you've already crawled via crawl_job against the candidate's resume.
		Returns {"match_score": 0-100, "reasoning": str}. Call this once per successfully crawled
		job, then call record_job_result(job_id) to persist it."""
		return _trace_tool_call("evaluate_match", {"job_id": job_id}, lambda: _evaluate_match_impl(job_id))

	def _evaluate_match_impl(job_id: int) -> dict[str, Any]:
		job = jobs_by_id.get(job_id)
		if job is None or phases.get(job_id) != "crawled":
			_record("evaluate_match", job_id, is_error=True, error_kind="guardrail")
			return {"error": f"job_id={job_id} has not been successfully crawled yet; call crawl_job first"}

		if job.evaluate_error is not None:
			phases[job_id] = "eval_error"
			_record("evaluate_match", job_id, is_error=True, error_kind="scripted")
			return {"error": job.evaluate_error}

		phases[job_id] = "evaluated"
		_record("evaluate_match", job_id, is_error=False, error_kind=None)
		assert job.evaluate_result is not None
		return job.evaluate_result

	@tool
	def record_job_result(job_id: int) -> str:
		"""Persist the evaluation for a job you've already scored via evaluate_match. Call this
		once per job, immediately after evaluate_match succeeds for it -- do not call it more than
		once for the same job_id, and never call it for a job_id evaluate_match returned an error
		for."""
		return _trace_tool_call("record_job_result", {"job_id": job_id}, lambda: _record_job_result_impl(job_id))

	def _record_job_result_impl(job_id: int) -> str:
		job = jobs_by_id.get(job_id)
		if job is None:
			_record("record_job_result", job_id, is_error=True, error_kind="guardrail")
			return f"unknown job_id={job_id}"

		phase = phases.get(job_id)
		if phase == "recorded":
			# Idempotent no-op, same as the real tool -- not an error, but still an extra call that
			# reduces call_volume_efficiency for this case.
			_record("record_job_result", job_id, is_error=False, error_kind=None)
			return f"job_id={job_id} was already recorded (no-op)"
		if phase != "evaluated":
			_record("record_job_result", job_id, is_error=True, error_kind="guardrail")
			return f"job_id={job_id} has not been evaluated yet; call evaluate_match first"

		phases[job_id] = "recorded"
		_record("record_job_result", job_id, is_error=False, error_kind=None)
		return f"recorded job_id={job_id}"

	return get_jobs_to_process, crawl_job, evaluate_match, record_job_result, calls, phases
