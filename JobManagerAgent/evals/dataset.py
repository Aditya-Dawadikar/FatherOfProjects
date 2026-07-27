from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Mirrors exactly what llm_providers.render_prompt() reads off a job dict (see crawler.fetch_job_detail
# for where these come from on the live path) -- an eval case's "job" object stands in for a crawled
# job page, so a case is fully self-contained and never depends on a live URL still being reachable.
REQUIRED_JOB_FIELDS = (
	"title",
	"company_name",
	"location",
	"job_type",
	"min_experience",
	"salary_range",
	"equity_range",
	"sponsors_visa",
	"skills",
	"description_text",
	"interview_process_text",
)


class DatasetError(ValueError):
	pass


@dataclass
class EvalCase:
	id: str
	job: dict[str, Any]
	expected_is_match: bool
	expected_score_min: int | None = None
	expected_score_max: int | None = None
	resume: str | None = None
	notes: str = ""


def _parse_case(raw: dict[str, Any], *, line_number: int) -> EvalCase:
	case_id = raw.get("id")
	if not isinstance(case_id, str) or not case_id:
		raise DatasetError(f"line {line_number}: 'id' is required and must be a non-empty string")

	job = raw.get("job")
	if not isinstance(job, dict):
		raise DatasetError(f"line {line_number} (id={case_id}): 'job' is required and must be an object")
	missing = [field for field in REQUIRED_JOB_FIELDS if field not in job]
	if missing:
		raise DatasetError(f"line {line_number} (id={case_id}): job is missing fields {missing}")

	expected_is_match = raw.get("expected_is_match")
	if not isinstance(expected_is_match, bool):
		raise DatasetError(
			f"line {line_number} (id={case_id}): 'expected_is_match' is required and must be true/false"
		)

	score_min = raw.get("expected_score_min")
	score_max = raw.get("expected_score_max")
	if (score_min is None) != (score_max is None):
		raise DatasetError(
			f"line {line_number} (id={case_id}): expected_score_min and expected_score_max must both be "
			"set or both omitted"
		)
	if score_min is not None:
		if not (isinstance(score_min, int) and isinstance(score_max, int) and 0 <= score_min <= score_max <= 100):
			raise DatasetError(
				f"line {line_number} (id={case_id}): expected_score_min/max must be integers with "
				"0 <= min <= max <= 100"
			)

	resume = raw.get("resume")
	if resume is not None and not isinstance(resume, str):
		raise DatasetError(f"line {line_number} (id={case_id}): 'resume' must be a string if provided")

	return EvalCase(
		id=case_id,
		job=job,
		expected_is_match=expected_is_match,
		expected_score_min=score_min,
		expected_score_max=score_max,
		resume=resume,
		notes=str(raw.get("notes") or ""),
	)


def load_golden_dataset(path: Path) -> list[EvalCase]:
	"""Parse a golden-dataset JSONL file (one EvalCase per line) into memory, failing fast with
	a line number and case id on the first malformed row rather than partially loading."""
	cases: list[EvalCase] = []
	seen_ids: set[str] = set()

	with path.open(encoding="utf-8") as handle:
		for line_number, raw_line in enumerate(handle, start=1):
			line = raw_line.strip()
			if not line:
				continue
			try:
				raw = json.loads(line)
			except json.JSONDecodeError as error:
				raise DatasetError(f"line {line_number}: invalid JSON: {error}") from error
			if not isinstance(raw, dict):
				raise DatasetError(f"line {line_number}: each line must be a JSON object")

			case = _parse_case(raw, line_number=line_number)
			if case.id in seen_ids:
				raise DatasetError(f"line {line_number}: duplicate case id {case.id!r}")
			seen_ids.add(case.id)
			cases.append(case)

	if not cases:
		raise DatasetError(f"{path} contains no eval cases")
	return cases
