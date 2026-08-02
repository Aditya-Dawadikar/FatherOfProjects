from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


TerminalState = Literal["crawl_error", "eval_error", "recorded"]


class ToolEvalDatasetError(ValueError):
	pass


@dataclass(frozen=True)
class ToolEvalJobCase:
	"""One job_id within a tool-eval scenario, plus the canned crawl/evaluate outcome the mock
	tools (mock_agent_tools.py) hand back when the agent under test calls crawl_job/evaluate_match
	for it. Exactly one of crawl_result/crawl_error is set, mirroring the real crawl_job tool's
	success-dict-or-error-dict return shape; evaluate_result/evaluate_error only apply when
	crawl_result is set, since the real workflow never evaluates a job it failed to crawl."""

	job_id: int
	job_role: str
	company_name: str
	crawl_result: dict[str, Any] | None
	crawl_error: str | None
	evaluate_result: dict[str, Any] | None
	evaluate_error: str | None

	@property
	def expected_terminal_state(self) -> TerminalState:
		if self.crawl_error is not None:
			return "crawl_error"
		if self.evaluate_error is not None:
			return "eval_error"
		return "recorded"

	@property
	def expected_call_count(self) -> int:
		"""How many tool calls a perfectly-behaved agent makes for this job_id: crawl_job always,
		plus evaluate_match unless crawl errored, plus record_job_result unless crawl or evaluate
		errored."""
		if self.crawl_error is not None:
			return 1
		if self.evaluate_error is not None:
			return 2
		return 3


@dataclass(frozen=True)
class ToolEvalCase:
	id: str
	jobs: list[ToolEvalJobCase]
	notes: str = ""

	@property
	def expected_call_count(self) -> int:
		"""+1 for the single get_jobs_to_process call every case expects, regardless of batch size
		(including an empty batch, which still expects exactly that one call)."""
		return 1 + sum(job.expected_call_count for job in self.jobs)

	@property
	def expected_trajectory(self) -> list[dict[str, Any]]:
		"""The golden tool-call plan as an openevals/agentevals-style trajectory (a list of
		OpenAI-format assistant messages, one tool call each) -- the `reference_outputs` fed to
		openevals.trajectory.match.create_trajectory_match_evaluator() in
		run_tool_selection_eval.py's plan_adherence metric. Derived from the same skip-on-error
		contract as expected_call_count/expected_terminal_state rather than hand-authored, so it
		can't drift from the workflow the system prompt actually describes."""
		messages: list[dict[str, Any]] = [tool_call_message("get_jobs_to_process", {})]
		for job in self.jobs:
			messages.append(tool_call_message("crawl_job", {"job_id": job.job_id}))
			if job.crawl_error is not None:
				continue
			messages.append(tool_call_message("evaluate_match", {"job_id": job.job_id}))
			if job.evaluate_error is not None:
				continue
			messages.append(tool_call_message("record_job_result", {"job_id": job.job_id}))
		return messages


def tool_call_message(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
	"""One openevals/agentevals-style trajectory message representing a single tool call --
	shared by ToolEvalCase.expected_trajectory (the golden plan) and
	run_tool_selection_eval.py's actual-trajectory builder (from the mock tools' call log), so
	both sides of the plan_adherence comparison are built the same way."""
	return {
		"role": "assistant",
		"content": "",
		"tool_calls": [{"function": {"name": tool_name, "arguments": json.dumps(args)}}],
	}


def _parse_job(raw: dict[str, Any], *, case_id: str, index: int) -> ToolEvalJobCase:
	def fail(message: str) -> ToolEvalDatasetError:
		return ToolEvalDatasetError(f"case {case_id!r} job[{index}]: {message}")

	job_id = raw.get("job_id")
	if not isinstance(job_id, int) or isinstance(job_id, bool):
		raise fail("'job_id' is required and must be an integer")

	job_role = raw.get("job_role")
	if not isinstance(job_role, str) or not job_role:
		raise fail("'job_role' is required and must be a non-empty string")

	company_name = raw.get("company_name")
	if not isinstance(company_name, str) or not company_name:
		raise fail("'company_name' is required and must be a non-empty string")

	crawl_result = raw.get("crawl_result")
	crawl_error = raw.get("crawl_error")
	if (crawl_result is None) == (crawl_error is None):
		raise fail("exactly one of 'crawl_result' or 'crawl_error' must be set")
	if crawl_result is not None and not isinstance(crawl_result, dict):
		raise fail("'crawl_result' must be an object")
	if crawl_error is not None and not isinstance(crawl_error, str):
		raise fail("'crawl_error' must be a string")

	evaluate_result = raw.get("evaluate_result")
	evaluate_error = raw.get("evaluate_error")

	if crawl_error is not None:
		if evaluate_result is not None or evaluate_error is not None:
			raise fail("'evaluate_result'/'evaluate_error' must be omitted when 'crawl_error' is set "
				"-- a job that fails to crawl is never evaluated")
	else:
		if (evaluate_result is None) == (evaluate_error is None):
			raise fail("exactly one of 'evaluate_result' or 'evaluate_error' must be set when "
				"'crawl_result' is set")
		if evaluate_error is not None and not isinstance(evaluate_error, str):
			raise fail("'evaluate_error' must be a string")
		if evaluate_result is not None:
			if not isinstance(evaluate_result, dict):
				raise fail("'evaluate_result' must be an object")
			score = evaluate_result.get("match_score")
			reasoning = evaluate_result.get("reasoning")
			if not (isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100):
				raise fail("evaluate_result.match_score must be an integer between 0 and 100")
			if not isinstance(reasoning, str):
				raise fail("evaluate_result.reasoning must be a string")

	return ToolEvalJobCase(
		job_id=job_id,
		job_role=job_role,
		company_name=company_name,
		crawl_result=crawl_result,
		crawl_error=crawl_error,
		evaluate_result=evaluate_result,
		evaluate_error=evaluate_error,
	)


def _parse_case(raw: dict[str, Any], *, line_number: int) -> ToolEvalCase:
	case_id = raw.get("id")
	if not isinstance(case_id, str) or not case_id:
		raise ToolEvalDatasetError(f"line {line_number}: 'id' is required and must be a non-empty string")

	raw_jobs = raw.get("jobs")
	if not isinstance(raw_jobs, list):
		raise ToolEvalDatasetError(f"line {line_number} (id={case_id}): 'jobs' is required and must be an array")

	jobs = [_parse_job(raw_job, case_id=case_id, index=i) for i, raw_job in enumerate(raw_jobs)]
	seen_job_ids = set()
	for job in jobs:
		if job.job_id in seen_job_ids:
			raise ToolEvalDatasetError(f"line {line_number} (id={case_id}): duplicate job_id {job.job_id}")
		seen_job_ids.add(job.job_id)

	return ToolEvalCase(id=case_id, jobs=jobs, notes=str(raw.get("notes") or ""))


def load_tool_eval_dataset(path: Path) -> list[ToolEvalCase]:
	"""Parse a tool-eval golden-dataset JSONL file (one ToolEvalCase per line) into memory,
	failing fast with a line number and case id on the first malformed row rather than partially
	loading -- same contract as evals/dataset.py's load_golden_dataset()."""
	cases: list[ToolEvalCase] = []
	seen_ids: set[str] = set()

	with path.open(encoding="utf-8") as handle:
		for line_number, raw_line in enumerate(handle, start=1):
			line = raw_line.strip()
			if not line:
				continue
			try:
				raw = json.loads(line)
			except json.JSONDecodeError as error:
				raise ToolEvalDatasetError(f"line {line_number}: invalid JSON: {error}") from error
			if not isinstance(raw, dict):
				raise ToolEvalDatasetError(f"line {line_number}: each line must be a JSON object")

			case = _parse_case(raw, line_number=line_number)
			if case.id in seen_ids:
				raise ToolEvalDatasetError(f"line {line_number}: duplicate case id {case.id!r}")
			seen_ids.add(case.id)
			cases.append(case)

	if not cases:
		raise ToolEvalDatasetError(f"{path} contains no eval cases")
	return cases
