from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


GuardrailCategory = Literal["output_validation", "injection"]


class GuardrailEvalDatasetError(ValueError):
	pass


@dataclass(frozen=True)
class GuardrailEvalCase:
	"""One "should this guardrail fire" scenario. Exercises the guardrail check functions
	directly (guardrails/checks.py's check_output, guardrails/injection.py's
	scan_job_for_injection) rather than a full agent run -- no LLM calls, since a case supplies
	the canned model output (for output_validation) or scraped job content (for injection) the
	check would see, not a resume/job pair for a real model to score.

	Exactly one of `llm_output` (category="output_validation") or `job` (category="injection") is
	set, matching which check function the case exercises."""

	id: str
	category: GuardrailCategory
	expected_triggered: bool
	expected_guardrail: str | None
	job: dict[str, Any] | None = None
	llm_output: dict[str, Any] | None = None
	notes: str = ""


def _parse_case(raw: dict[str, Any], *, line_number: int) -> GuardrailEvalCase:
	def fail(message: str) -> GuardrailEvalDatasetError:
		return GuardrailEvalDatasetError(f"line {line_number}: {message}")

	case_id = raw.get("id")
	if not isinstance(case_id, str) or not case_id:
		raise fail("'id' is required and must be a non-empty string")

	def fail_case(message: str) -> GuardrailEvalDatasetError:
		return GuardrailEvalDatasetError(f"line {line_number} (id={case_id}): {message}")

	category = raw.get("category")
	if category not in ("output_validation", "injection"):
		raise fail_case("'category' must be 'output_validation' or 'injection'")

	expected_triggered = raw.get("expected_triggered")
	if not isinstance(expected_triggered, bool):
		raise fail_case("'expected_triggered' is required and must be true/false")

	expected_guardrail = raw.get("expected_guardrail")
	if expected_guardrail is not None and not isinstance(expected_guardrail, str):
		raise fail_case("'expected_guardrail' must be a string if provided")
	if expected_triggered and not expected_guardrail:
		raise fail_case("'expected_guardrail' is required when expected_triggered is true")

	job = raw.get("job")
	llm_output = raw.get("llm_output")

	if category == "injection":
		if not isinstance(job, dict):
			raise fail_case("'job' is required for category='injection'")
		if llm_output is not None:
			raise fail_case("'llm_output' must be omitted for category='injection'")
	else:
		if not isinstance(llm_output, dict):
			raise fail_case("'llm_output' is required for category='output_validation'")
		score = llm_output.get("match_score")
		reasoning = llm_output.get("reasoning")
		if not (isinstance(score, int) and not isinstance(score, bool)):
			raise fail_case("llm_output.match_score must be an integer")
		if not isinstance(reasoning, str):
			raise fail_case("llm_output.reasoning must be a string")
		if job is not None and not isinstance(job, dict):
			raise fail_case("'job' must be an object if provided")

	return GuardrailEvalCase(
		id=case_id,
		category=category,
		expected_triggered=expected_triggered,
		expected_guardrail=expected_guardrail,
		job=job,
		llm_output=llm_output,
		notes=str(raw.get("notes") or ""),
	)


def load_guardrail_eval_dataset(path: Path) -> list[GuardrailEvalCase]:
	"""Parse a guardrails golden-dataset JSONL file (one GuardrailEvalCase per line) into memory,
	failing fast with a line number and case id on the first malformed row -- same contract as
	evals/dataset.py's load_golden_dataset() and evals/tool_eval_dataset.py's
	load_tool_eval_dataset()."""
	cases: list[GuardrailEvalCase] = []
	seen_ids: set[str] = set()

	with path.open(encoding="utf-8") as handle:
		for line_number, raw_line in enumerate(handle, start=1):
			line = raw_line.strip()
			if not line:
				continue
			try:
				raw = json.loads(line)
			except json.JSONDecodeError as error:
				raise GuardrailEvalDatasetError(f"line {line_number}: invalid JSON: {error}") from error
			if not isinstance(raw, dict):
				raise GuardrailEvalDatasetError(f"line {line_number}: each line must be a JSON object")

			case = _parse_case(raw, line_number=line_number)
			if case.id in seen_ids:
				raise GuardrailEvalDatasetError(f"line {line_number}: duplicate case id {case.id!r}")
			seen_ids.add(case.id)
			cases.append(case)

	if not cases:
		raise GuardrailEvalDatasetError(f"{path} contains no eval cases")
	return cases
