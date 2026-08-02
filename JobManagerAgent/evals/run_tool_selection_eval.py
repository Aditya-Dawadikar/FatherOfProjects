"""Offline eval harness: drives the real ReAct orchestrator (agents/react_agent.py's system
prompt, a real LLM deciding which tool to call next) against a fixed, curated golden dataset of
mocked tool scenarios (see tool_eval_dataset.py for the JSONL schema), instead of a live DB/
crawler/scoring model -- so tool-selection quality can be measured deterministically and cheaply
compared to a full live cycle.

Five metrics per case (averaged into a dataset-level summary):
  - tool_selection_accuracy: of {get_jobs_to_process once, then per job: crawl -> evaluate-or-skip
    -> record-or-skip}, the fraction the agent got right (right tool, right order, no guardrail
    violation touching that job). Custom scoring -- openevals has no notion of our per-job
    skip-on-error contract, so this stays home-grown.
  - tool_error_rate: fraction of tool calls that errored *because the agent violated the tool
    contract* (unknown job_id, out-of-order call, duplicate call) -- not counting scripted
    errors the scenario deliberately set up (e.g. a 404), tracked separately as scripted_errors.
  - call_volume_efficiency: how close the agent's total call count came to the minimum needed,
    symmetric in both directions (extra and missing calls both reduce it).
  - plan_adherence: whether the agent's actual sequence of (tool, args) calls exactly matches the
    golden plan derived from the case (ToolEvalCase.expected_trajectory), order-insensitive,
    scored via openevals.trajectory.match.create_trajectory_match_evaluator(mode="unordered") --
    unlike tool_selection_accuracy this is call-level (it also catches a call made with the wrong
    job_id, or an extra hallucinated call, even if every job still happened to land on its
    correct terminal state).
  - consistency_score: each case is run `repeats` times (default 3 -- the golden dataset is small
    enough that this is cheap); consistency_score is the fraction of the C(repeats, 2) pairs of
    independent runs whose trajectories exactly match each other (same openevals evaluator,
    actual-vs-actual instead of actual-vs-golden). Low consistency flags a case where the
    orchestrator's tool-selection behavior isn't stable run to run, independent of whether any
    given run was "correct".

Plus a cost metric, also only meaningful because of the repeated runs above:
  - cost_per_successful_run: total orchestrator LLM spend across a case's `repeats` trials,
    divided by how many of those trials actually succeeded (plan_adherence and not incomplete),
    not by the raw trial count. A run that's individually cheap but only succeeds half the time
    has double the *effective* cost of a getting a correct run out of it -- attributing the failed
    trials' spend only to the trials that worked is the point, as opposed to mean_cost_per_run
    (total spend / repeats), which is reported alongside it for contrast. Undefined (None/omitted)
    for a case with zero successful trials, since cost-per-success is infinite there, not zero.
    Token usage is collected via a LangChain callback on agent.invoke() (not its return value, for
    the same GraphRecursionError-robustness reason _trajectory_from_calls() avoids it) and priced
    with utils/llm_pricing.py.

Usage (from JobManagerAgent/):
    venv\\Scripts\\python evals\\run_tool_selection_eval.py --dataset evals\\tool_selection_golden_dataset.jsonl
    venv\\Scripts\\python evals\\run_tool_selection_eval.py --dataset evals\\tool_selection_golden_dataset.jsonl --limit 3 --repeats 1
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mlflow  # noqa: E402
from langchain.agents import create_agent  # noqa: E402
from langchain_core.callbacks import BaseCallbackHandler  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.outputs import LLMResult  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402
from openevals.trajectory.match import create_trajectory_match_evaluator  # noqa: E402

from agents.react_agent import _system_prompt, build_llm  # noqa: E402
from evals.mock_agent_tools import build_mock_agent_tools  # noqa: E402
from evals.tool_eval_dataset import (  # noqa: E402
	ToolEvalCase,
	ToolEvalDatasetError,
	load_tool_eval_dataset,
	tool_call_message,
)
from utils.agent_logger import configure_logging, get_agent_logger, new_id  # noqa: E402
from utils.config import DEFAULT_MODEL, RECURSION_LIMIT_HEADROOM, STEPS_PER_JOB, load_match_threshold, load_resume  # noqa: E402
from utils.llm_pricing import estimate_cost_usd  # noqa: E402
from utils.mlflow_utils import (  # noqa: E402
	ensure_tracking_uri_configured,
	get_tracking_uri,
	load_mlflow_tool_eval_experiment_name,
	set_experiment_safely,
)


configure_logging()
LOGGER = get_agent_logger(__name__)

DEFAULT_REPEATS = 3

# Order-insensitive, args-exact trajectory match -- used both for plan_adherence (actual vs the
# golden reference trajectory) and consistency_score (actual vs actual, across repeats of the
# same case). A single instance is reusable since it's stateless.
_TRAJECTORY_MATCH_EVALUATOR = create_trajectory_match_evaluator(
	trajectory_match_mode="unordered", tool_args_match_mode="exact"
)


class _UsageCollector(BaseCallbackHandler):
	"""Accumulates orchestrator LLM token usage across every turn of one agent.invoke() call, via
	LangChain's on_llm_end hook rather than reading agent.invoke()'s return value -- callbacks
	fire synchronously as each turn completes, so usage collected so far survives a
	GraphRecursionError that aborts the overall invoke() before it can return anything."""

	def __init__(self) -> None:
		self.input_tokens = 0
		self.output_tokens = 0

	def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
		for generation_list in response.generations:
			for generation in generation_list:
				message = getattr(generation, "message", None)
				usage = getattr(message, "usage_metadata", None) if message is not None else None
				if usage:
					self.input_tokens += usage.get("input_tokens") or 0
					self.output_tokens += usage.get("output_tokens") or 0


def _trajectory_from_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Rebuilds the actual tool-call trajectory from the mock tools' call log (populated live as
	each call happens) rather than from agent.invoke()'s return value -- that keeps plan_adherence
	and consistency_score accurate even when the run hits GraphRecursionError, since `calls` is
	mutated in place through the exception while agent.invoke() itself never returns."""
	return [
		tool_call_message(call["tool"], {"job_id": call["job_id"]} if call["job_id"] is not None else {})
		for call in calls
	]


def _score_trial(case: ToolEvalCase, calls: list[dict[str, Any]], phases: dict[int, str], *, incomplete: bool) -> dict[str, Any]:
	expected_call_count = case.expected_call_count
	actual_call_count = len(calls)
	guardrail_errors = sum(1 for call in calls if call["error_kind"] == "guardrail")
	scripted_errors = sum(1 for call in calls if call["error_kind"] == "scripted")
	tool_error_rate = (guardrail_errors / actual_call_count) if actual_call_count else 0.0

	fetched_first_correctly = bool(calls) and calls[0]["tool"] == "get_jobs_to_process" and not calls[0]["is_error"]
	correct_steps = 1 if fetched_first_correctly else 0
	for job in case.jobs:
		touched_guardrail = any(
			call["job_id"] == job.job_id and call["error_kind"] == "guardrail" for call in calls
		)
		if not touched_guardrail and phases.get(job.job_id) == job.expected_terminal_state:
			correct_steps += 1
	total_steps = 1 + len(case.jobs)
	tool_selection_accuracy = correct_steps / total_steps

	call_volume_efficiency = max(0.0, 1 - abs(actual_call_count - expected_call_count) / expected_call_count)

	return {
		"actual_call_count": actual_call_count,
		"tool_selection_accuracy": tool_selection_accuracy,
		"guardrail_errors": guardrail_errors,
		"scripted_errors": scripted_errors,
		"tool_error_rate": tool_error_rate,
		"call_volume_efficiency": call_volume_efficiency,
		"incomplete": incomplete,
	}


def _run_one_trial(
	*, case: ToolEvalCase, llm: Any, model_name: str, resume_text: str, threshold: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
	get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool, calls, phases = build_mock_agent_tools(case)
	agent = create_agent(
		llm,
		tools=[get_jobs_tool, crawl_job_tool, evaluate_match_tool, record_result_tool],
		system_prompt=_system_prompt(resume_text, threshold),
	)

	recursion_limit = len(case.jobs) * STEPS_PER_JOB + RECURSION_LIMIT_HEADROOM
	incomplete = False
	usage = _UsageCollector()
	try:
		agent.invoke(
			{"messages": [HumanMessage(content="Begin.")]},
			config={"recursion_limit": recursion_limit, "callbacks": [usage]},
		)
	except GraphRecursionError:
		incomplete = True

	trial = _score_trial(case, calls, phases, incomplete=incomplete)
	trajectory = _trajectory_from_calls(calls)
	adherence = _TRAJECTORY_MATCH_EVALUATOR(outputs=trajectory, reference_outputs=case.expected_trajectory)
	trial["plan_adherence"] = bool(adherence["score"])
	trial["succeeded"] = trial["plan_adherence"] and not incomplete
	trial["input_tokens"] = usage.input_tokens
	trial["output_tokens"] = usage.output_tokens
	trial["cost_usd"] = estimate_cost_usd(model_name, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
	return trial, trajectory


def _score_consistency(trajectories: list[list[dict[str, Any]]]) -> float:
	pairs = list(itertools.combinations(range(len(trajectories)), 2))
	if not pairs:
		return 1.0
	matches = sum(
		1
		for i, j in pairs
		if _TRAJECTORY_MATCH_EVALUATOR(outputs=trajectories[i], reference_outputs=trajectories[j])["score"]
	)
	return matches / len(pairs)


def _run_case(
	*, case: ToolEvalCase, llm: Any, model_name: str, resume_text: str, threshold: int, repeats: int
) -> dict[str, Any]:
	trials: list[dict[str, Any]] = []
	trajectories: list[list[dict[str, Any]]] = []
	for _ in range(repeats):
		trial, trajectory = _run_one_trial(
			case=case, llm=llm, model_name=model_name, resume_text=resume_text, threshold=threshold
		)
		trials.append(trial)
		trajectories.append(trajectory)

	cost_usd = sum(trial["cost_usd"] for trial in trials)
	successful_trials = sum(1 for trial in trials if trial["succeeded"])

	return {
		"id": case.id,
		"num_jobs": len(case.jobs),
		"repeats": repeats,
		"expected_call_count": case.expected_call_count,
		"total_actual_calls": sum(trial["actual_call_count"] for trial in trials),
		"tool_selection_accuracy": sum(trial["tool_selection_accuracy"] for trial in trials) / repeats,
		"tool_error_rate": sum(trial["tool_error_rate"] for trial in trials) / repeats,
		"call_volume_efficiency": sum(trial["call_volume_efficiency"] for trial in trials) / repeats,
		"plan_adherence": sum(1 for trial in trials if trial["plan_adherence"]) / repeats,
		"consistency_score": _score_consistency(trajectories) if repeats >= 2 else None,
		"guardrail_errors": sum(trial["guardrail_errors"] for trial in trials),
		"scripted_errors": sum(trial["scripted_errors"] for trial in trials),
		"incomplete_trials": sum(1 for trial in trials if trial["incomplete"]),
		"input_tokens": sum(trial["input_tokens"] for trial in trials),
		"output_tokens": sum(trial["output_tokens"] for trial in trials),
		"cost_usd": cost_usd,
		"successful_trials": successful_trials,
		"success_rate": successful_trials / repeats,
		"mean_cost_per_run": cost_usd / repeats,
		"cost_per_successful_run": (cost_usd / successful_trials) if successful_trials else None,
		"error": None,
	}


def _error_row(case: ToolEvalCase, repeats: int, error_message: str) -> dict[str, Any]:
	return {
		"id": case.id,
		"num_jobs": len(case.jobs),
		"repeats": repeats,
		"expected_call_count": case.expected_call_count,
		"total_actual_calls": None,
		"tool_selection_accuracy": None,
		"tool_error_rate": None,
		"call_volume_efficiency": None,
		"plan_adherence": None,
		"consistency_score": None,
		"guardrail_errors": None,
		"scripted_errors": None,
		"incomplete_trials": None,
		"input_tokens": None,
		"output_tokens": None,
		"cost_usd": None,
		"successful_trials": None,
		"success_rate": None,
		"mean_cost_per_run": None,
		"cost_per_successful_run": None,
		"error": error_message,
	}


ROW_COLUMNS = (
	"id",
	"num_jobs",
	"repeats",
	"expected_call_count",
	"total_actual_calls",
	"tool_selection_accuracy",
	"tool_error_rate",
	"call_volume_efficiency",
	"plan_adherence",
	"consistency_score",
	"guardrail_errors",
	"scripted_errors",
	"incomplete_trials",
	"input_tokens",
	"output_tokens",
	"cost_usd",
	"successful_trials",
	"success_rate",
	"mean_cost_per_run",
	"cost_per_successful_run",
	"error",
)


def _rows_to_columns(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
	return {column: [row.get(column) for row in rows] for column in ROW_COLUMNS}


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
	values = [row[key] for row in rows if row[key] is not None]
	return sum(values) / len(values) if values else None


def _compute_summary(rows: list[dict[str, Any]], *, total_cases: int, repeats: int) -> dict[str, Any]:
	scored = [row for row in rows if row["error"] is None]
	errored_count = len(rows) - len(scored)
	total_trials = len(scored) * repeats

	total_cost_usd = sum(row["cost_usd"] for row in scored)
	total_successful_trials = sum(row["successful_trials"] for row in scored)

	summary: dict[str, Any] = {
		"total_cases": total_cases,
		"evaluated_cases": len(scored),
		"errored_cases": errored_count,
		"repeats": repeats,
		"total_trials": total_trials,
		"incomplete_trials": sum(row["incomplete_trials"] for row in scored),
		"total_expected_calls": sum(row["expected_call_count"] for row in scored),
		"total_actual_calls": sum(row["total_actual_calls"] for row in scored),
		"total_guardrail_errors": sum(row["guardrail_errors"] for row in scored),
		"total_scripted_errors": sum(row["scripted_errors"] for row in scored),
		"total_input_tokens": sum(row["input_tokens"] for row in scored),
		"total_output_tokens": sum(row["output_tokens"] for row in scored),
		"total_cost_usd": total_cost_usd,
		"total_successful_trials": total_successful_trials,
	}
	for key in ("tool_selection_accuracy", "tool_error_rate", "call_volume_efficiency", "plan_adherence", "consistency_score"):
		value = _mean(scored, key)
		if value is not None:
			summary[key] = value
	if total_trials:
		summary["mean_calls_per_trial"] = summary["total_actual_calls"] / total_trials
		summary["success_rate"] = total_successful_trials / total_trials
		summary["mean_cost_per_run"] = total_cost_usd / total_trials
	if total_successful_trials:
		# Undefined (omitted, not zero) when nothing succeeded -- a 0%-success case's cost-to-success
		# is infinite, not free; see the module docstring on why this is spend-per-success, not
		# spend-per-attempt (mean_cost_per_run above already covers the latter).
		summary["cost_per_successful_run"] = total_cost_usd / total_successful_trials
	return summary


def run_tool_selection_eval(
	*,
	eval_id: str | None = None,
	dataset_path: Path,
	model: str | None,
	threshold: int | None,
	experiment_name: str | None,
	run_name: str | None,
	limit: int | None,
	repeats: int | None = None,
) -> dict[str, Any]:
	eval_id = eval_id or new_id()
	repeats = repeats if repeats is not None else DEFAULT_REPEATS
	if repeats < 1:
		raise ValueError(f"repeats must be >= 1, got {repeats}")
	log = LOGGER.bind(eval_id=eval_id)

	ensure_tracking_uri_configured()
	resolved_experiment_name = experiment_name or load_mlflow_tool_eval_experiment_name()
	set_experiment_safely(resolved_experiment_name)
	log.action("mlflow_target", tracking_uri=get_tracking_uri(), experiment_name=resolved_experiment_name, repeats=repeats)

	rows: list[dict[str, Any]] = []
	with mlflow.start_run(run_name=run_name or f"tool-eval-{eval_id}"):
		run = mlflow.active_run()
		run_id = run.info.run_id if run is not None else None
		if run_id is not None:
			log.action("mlflow_run_started", run_id=run_id)
		mlflow.set_tags(
			{
				"eval_id": eval_id,
				"run_type": "tool_selection_eval",
				"dataset_path": str(dataset_path),
			}
		)
		try:
			cases = load_tool_eval_dataset(dataset_path)
			if limit is not None:
				cases = cases[:limit]
			log.action("dataset_loaded", dataset=str(dataset_path), case_count=len(cases))

			resolved_model = model or DEFAULT_MODEL
			resolved_threshold = threshold if threshold is not None else load_match_threshold()
			resume_text = load_resume()
			llm = build_llm(resolved_model)
		except Exception as error:
			message = f"Invalid golden dataset: {error}" if isinstance(error, ToolEvalDatasetError) else str(error)
			mlflow.set_tag("error_message", message)
			raise

		with mlflow.start_span(
			name="tool_selection_eval",
			span_type="EVALUATOR",
			attributes={"eval_id": eval_id, "llm_model": resolved_model, "repeats": repeats},
			run_id=run_id,
		) as eval_span:
			try:
				eval_span.set_inputs({"dataset_path": str(dataset_path), "dataset_case_count": len(cases), "repeats": repeats})
				mlflow.log_params(
					{
						"llm_model": resolved_model,
						"match_threshold": resolved_threshold,
						"dataset_case_count": len(cases),
						"repeats": repeats,
						**({"limit": limit} if limit is not None else {}),
					}
				)
				mlflow.log_artifact(str(dataset_path))

				for case in cases:
					case_log = log.bind(case_id=case.id)
					try:
						with mlflow.start_span(
							name="eval_case", span_type="TASK", attributes={"case_id": case.id, "repeats": repeats}
						) as case_span:
							case_span.set_inputs({"num_jobs": len(case.jobs), "expected_call_count": case.expected_call_count})
							row = _run_case(
								case=case,
								llm=llm,
								model_name=resolved_model,
								resume_text=resume_text,
								threshold=resolved_threshold,
								repeats=repeats,
							)
							case_span.set_outputs(
								{
									"tool_selection_accuracy": row["tool_selection_accuracy"],
									"tool_error_rate": row["tool_error_rate"],
									"call_volume_efficiency": row["call_volume_efficiency"],
									"plan_adherence": row["plan_adherence"],
									"consistency_score": row["consistency_score"],
									"success_rate": row["success_rate"],
									"cost_usd": row["cost_usd"],
									"cost_per_successful_run": row["cost_per_successful_run"],
								}
							)
						case_log.action(
							"case_scored",
							tool_selection_accuracy=row["tool_selection_accuracy"],
							tool_error_rate=row["tool_error_rate"],
							call_volume_efficiency=row["call_volume_efficiency"],
							plan_adherence=row["plan_adherence"],
							consistency_score=row["consistency_score"],
							cost_usd=row["cost_usd"],
							cost_per_successful_run=row["cost_per_successful_run"],
						)
						rows.append(row)
					except Exception as error:
						case_log.action("case_errored", error=str(error))
						rows.append(_error_row(case, repeats, str(error)))

				summary = _compute_summary(rows, total_cases=len(cases), repeats=repeats)
				mlflow.log_metrics({key: value for key, value in summary.items() if isinstance(value, (int, float))})
				mlflow.log_table(data=_rows_to_columns(rows), artifact_file="tool_eval_results.json")
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
		description="Run the tool-selection eval harness against a golden dataset of mocked tool scenarios."
	)
	parser.add_argument("--dataset", required=True, type=Path, help="Path to a tool-eval golden-dataset JSONL file.")
	parser.add_argument("--model", default=None, help="Overrides the orchestrator LLM model (defaults to DEFAULT_MODEL).")
	parser.add_argument("--threshold", type=int, default=None, help="Overrides MATCH_THRESHOLD for the system prompt text.")
	parser.add_argument("--experiment-name", default=None, help="Overrides MLFLOW_TOOL_EVAL_EXPERIMENT_NAME.")
	parser.add_argument("--run-name", default=None, help="MLflow run name; defaults to tool-eval-<eval_id>.")
	parser.add_argument("--limit", type=int, default=None, help="Only score the first N cases (smoke testing).")
	parser.add_argument(
		"--repeats",
		type=int,
		default=None,
		help=f"How many independent times to run each case (default {DEFAULT_REPEATS}) -- needed to "
		"compute consistency_score, and averages the other metrics over more than one sample.",
	)
	return parser.parse_args()


def main() -> None:
	args = _parse_args()
	try:
		summary = run_tool_selection_eval(
			dataset_path=args.dataset,
			model=args.model,
			threshold=args.threshold,
			experiment_name=args.experiment_name,
			run_name=args.run_name,
			limit=args.limit,
			repeats=args.repeats,
		)
	except ToolEvalDatasetError as error:
		raise SystemExit(f"Invalid golden dataset: {error}") from error

	print("\nTool-selection eval summary:")
	for key, value in summary.items():
		print(f"  {key}: {value}")


if __name__ == "__main__":
	main()
