"""Offline eval harness: measures the guardrail checks themselves (guardrails/checks.py's
output-validation and guardrails/injection.py's prompt-injection screen) against a fixed, labeled
golden dataset of "should this guardrail fire" scenarios (see guardrail_eval_dataset.py for the
JSONL schema) -- same accuracy/precision/recall/f1 shape as run_offline_eval.py, but scoring
guardrail effectiveness instead of match quality.

No LLM calls: each case supplies either a canned LLM output (for output_validation) or crawled
job content (for injection) and asserts whether the guardrail fires, so this is
fast/free/deterministic and safe to run on every guardrail-logic change, unlike the two eval
harnesses above it which both make real, billed model calls.

Usage (from JobManagerAgent/):
    venv\\Scripts\\python evals\\run_guardrails_eval.py --dataset evals\\guardrails_golden_dataset.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mlflow  # noqa: E402

from evals.guardrail_eval_dataset import (  # noqa: E402
	GuardrailEvalCase,
	GuardrailEvalDatasetError,
	load_guardrail_eval_dataset,
)
from guardrails.checks import check_output  # noqa: E402
from guardrails.errors import GuardrailBlockedError  # noqa: E402
from guardrails.injection import scan_job_for_injection  # noqa: E402
from utils.agent_logger import configure_logging, get_agent_logger, new_id  # noqa: E402
from utils.mlflow_utils import (  # noqa: E402
	ensure_tracking_uri_configured,
	get_tracking_uri,
	load_mlflow_guardrails_eval_experiment_name,
	set_experiment_safely,
)


configure_logging()
LOGGER = get_agent_logger(__name__)


def _run_one_case(case: GuardrailEvalCase) -> dict[str, Any]:
	triggered = False
	triggered_guardrail: str | None = None
	try:
		if case.category == "injection":
			assert case.job is not None
			scan_job_for_injection(job_id=None, job=case.job)
		else:
			assert case.llm_output is not None
			check_output(
				job_id=None,
				match_score=case.llm_output["match_score"],
				reasoning=case.llm_output["reasoning"],
			)
	except GuardrailBlockedError as error:
		triggered = True
		triggered_guardrail = error.guardrail

	correct = triggered == case.expected_triggered
	# Only meaningful when a trigger was expected -- a case where neither side triggered has
	# nothing to compare guardrail names against, so it can't be "wrong" on this axis.
	guardrail_correct = (not case.expected_triggered) or (triggered_guardrail == case.expected_guardrail)

	return {
		"id": case.id,
		"category": case.category,
		"expected_triggered": case.expected_triggered,
		"expected_guardrail": case.expected_guardrail,
		"triggered": triggered,
		"triggered_guardrail": triggered_guardrail,
		"correct": correct,
		"guardrail_correct": guardrail_correct,
	}


ROW_COLUMNS = (
	"id",
	"category",
	"expected_triggered",
	"expected_guardrail",
	"triggered",
	"triggered_guardrail",
	"correct",
	"guardrail_correct",
)


def _rows_to_columns(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
	return {column: [row.get(column) for row in rows] for column in ROW_COLUMNS}


def _compute_summary(rows: list[dict[str, Any]], *, total_cases: int) -> dict[str, Any]:
	tp = sum(1 for row in rows if row["triggered"] and row["expected_triggered"])
	fp = sum(1 for row in rows if row["triggered"] and not row["expected_triggered"])
	fn = sum(1 for row in rows if not row["triggered"] and row["expected_triggered"])
	tn = sum(1 for row in rows if not row["triggered"] and not row["expected_triggered"])

	accuracy = (tp + tn) / len(rows) if rows else None
	precision = tp / (tp + fp) if (tp + fp) > 0 else None
	recall = tp / (tp + fn) if (tp + fn) > 0 else None
	f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
	guardrail_id_accuracy = (sum(1 for row in rows if row["guardrail_correct"]) / len(rows)) if rows else None

	summary: dict[str, Any] = {
		"total_cases": total_cases,
		"evaluated_cases": len(rows),
		"true_positive": tp,
		"false_positive": fp,
		"false_negative": fn,
		"true_negative": tn,
	}
	if accuracy is not None:
		summary["accuracy"] = accuracy
	if precision is not None:
		summary["precision"] = precision
	if recall is not None:
		summary["recall"] = recall
	if f1 is not None:
		summary["f1"] = f1
	if guardrail_id_accuracy is not None:
		summary["guardrail_id_accuracy"] = guardrail_id_accuracy
	return summary


def run_guardrails_eval(
	*,
	eval_id: str | None = None,
	dataset_path: Path,
	experiment_name: str | None,
	run_name: str | None,
	limit: int | None,
) -> dict[str, Any]:
	eval_id = eval_id or new_id()
	log = LOGGER.bind(eval_id=eval_id)

	ensure_tracking_uri_configured()
	resolved_experiment_name = experiment_name or load_mlflow_guardrails_eval_experiment_name()
	set_experiment_safely(resolved_experiment_name)
	log.action("mlflow_target", tracking_uri=get_tracking_uri(), experiment_name=resolved_experiment_name)

	rows: list[dict[str, Any]] = []
	with mlflow.start_run(run_name=run_name or f"guardrails-eval-{eval_id}"):
		run = mlflow.active_run()
		run_id = run.info.run_id if run is not None else None
		if run_id is not None:
			log.action("mlflow_run_started", run_id=run_id)
		mlflow.set_tags(
			{
				"eval_id": eval_id,
				"run_type": "guardrails_eval",
				"dataset_path": str(dataset_path),
			}
		)
		try:
			cases = load_guardrail_eval_dataset(dataset_path)
			if limit is not None:
				cases = cases[:limit]
			log.action("dataset_loaded", dataset=str(dataset_path), case_count=len(cases))
		except Exception as error:
			message = f"Invalid golden dataset: {error}" if isinstance(error, GuardrailEvalDatasetError) else str(error)
			mlflow.set_tag("error_message", message)
			raise

		with mlflow.start_span(
			name="guardrails_eval",
			span_type="EVALUATOR",
			attributes={"eval_id": eval_id},
			run_id=run_id,
		) as eval_span:
			try:
				eval_span.set_inputs({"dataset_path": str(dataset_path), "dataset_case_count": len(cases)})
				params: dict[str, Any] = {"dataset_case_count": len(cases)}
				if limit is not None:
					params["limit"] = limit
				mlflow.log_params(params)
				mlflow.log_artifact(str(dataset_path))

				for case in cases:
					case_log = log.bind(case_id=case.id)
					with mlflow.start_span(
						name="eval_case",
						span_type="TASK",
						attributes={"case_id": case.id, "category": case.category},
					) as case_span:
						case_span.set_inputs({"category": case.category, "expected_triggered": case.expected_triggered})
						row = _run_one_case(case)
						case_span.set_outputs({"triggered": row["triggered"], "correct": row["correct"]})
					case_log.action("case_scored", triggered=row["triggered"], correct=row["correct"])
					rows.append(row)

				summary = _compute_summary(rows, total_cases=len(cases))
				mlflow.log_metrics({key: value for key, value in summary.items() if isinstance(value, (int, float))})
				mlflow.log_table(data=_rows_to_columns(rows), artifact_file="guardrails_eval_results.json")
				eval_span.set_outputs(summary)
				mlflow.set_tag("trace_id", eval_span.trace_id)
				log.action("mlflow_trace_ready", trace_id=eval_span.trace_id)
			except Exception as error:
				mlflow.set_tag("error_message", str(error))
				raise

	mlflow.flush_trace_async_logging(terminate=False)

	log.action("eval_complete", **summary)
	return summary


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Run the guardrails eval harness against a golden dataset of trigger/no-trigger scenarios."
	)
	parser.add_argument("--dataset", required=True, type=Path, help="Path to a guardrails golden-dataset JSONL file.")
	parser.add_argument("--experiment-name", default=None, help="Overrides MLFLOW_GUARDRAILS_EVAL_EXPERIMENT_NAME.")
	parser.add_argument("--run-name", default=None, help="MLflow run name; defaults to guardrails-eval-<eval_id>.")
	parser.add_argument("--limit", type=int, default=None, help="Only score the first N cases (smoke testing).")
	return parser.parse_args()


def main() -> None:
	args = _parse_args()
	try:
		summary = run_guardrails_eval(
			dataset_path=args.dataset,
			experiment_name=args.experiment_name,
			run_name=args.run_name,
			limit=args.limit,
		)
	except GuardrailEvalDatasetError as error:
		raise SystemExit(f"Invalid golden dataset: {error}") from error

	print("\nGuardrails eval summary:")
	for key, value in summary.items():
		print(f"  {key}: {value}")


if __name__ == "__main__":
	main()
