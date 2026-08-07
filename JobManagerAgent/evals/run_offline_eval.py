"""Offline eval harness: scores the job-match prompt/model against a fixed, labeled golden
dataset (see dataset.py for the JSONL schema) instead of live crawled jobs, so prompt/model
changes can be checked for regressions before they ever touch production traffic.

Usage (from JobManagerAgent/):
    venv\\Scripts\\python evals\\run_offline_eval.py --dataset evals\\golden_dataset.jsonl
    venv\\Scripts\\python evals\\run_offline_eval.py --dataset evals\\golden_dataset.jsonl --prompt-source local
	venv\\Scripts\\python evals\\run_offline_eval.py --dataset evals\\golden_dataset.jsonl --provider gemini
	venv\\Scripts\\python evals\\run_offline_eval.py --dataset evals\\golden_dataset.jsonl --prompt-version 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mlflow  # noqa: E402
from mlflow.entities.model_registry.prompt_version import PromptVersion  # noqa: E402
from mlflow.exceptions import MlflowException  # noqa: E402

from evals.dataset import DatasetError, EvalCase, load_golden_dataset  # noqa: E402
from guardrails.errors import GuardrailBlockedError  # noqa: E402
from integrations.mlflow import (  # noqa: E402
	PROMPT_ALIAS,
	PROMPT_FILE,
	PROMPT_NAME,
	LoadedPrompt,
	build_loaded_prompt,
	load_prompt_version,
)
from llm_providers import (  # noqa: E402
	MatchResponseError,
	RateLimitError,
	TransientProviderError,
	build_client,
	load_model_name,
	load_provider_name,
	score_job,
	score_jobs_batch,
)
from utils.agent_logger import configure_logging, get_agent_logger, new_id  # noqa: E402
from utils.config import load_backfill_batch_size, load_match_threshold, load_resume  # noqa: E402
from utils.mlflow_utils import (  # noqa: E402
	ensure_tracking_uri_configured,
	get_tracking_uri,
	load_mlflow_eval_experiment_name,
	set_experiment_safely,
)


configure_logging()
LOGGER = get_agent_logger(__name__)


def _load_prompt_version(source: str, version: int | None = None) -> LoadedPrompt:
	if source == "production":
		ensure_tracking_uri_configured()
		if version is not None:
			# Pins a specific point in the prompt's registered history (get_active_prompt() creates
			# a new version every time prompts/job_match_v1.txt's content changes) rather than
			# whichever version the 'production' alias currently points to -- lets a run be repeated
			# against an older version to compare against newer ones, e.g. to bisect a regression.
			try:
				return load_prompt_version(str(version))
			except MlflowException as error:
				raise SystemExit(f"No version {version} is registered for prompt '{PROMPT_NAME}': {error}") from error

		# Read-only alias lookup -- deliberately NOT get_active_prompt(), which would
		# auto-register prompts/job_match_v1.txt and move the 'production' alias if it had
		# drifted; an eval run must never have that side effect.
		prompt = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@{PROMPT_ALIAS}", allow_missing=True)
		if prompt is None:
			raise SystemExit(
				f"No prompt is registered under alias '{PROMPT_ALIAS}' yet. Run the live agent once "
				"first, or pass --prompt-source local to eval prompts/job_match_v1.txt directly."
			)
		return build_loaded_prompt(prompt)

	if source == "local":
		if version is not None:
			raise ValueError("--prompt-version only applies to --prompt-source production; "
				"'local' always scores prompts/job_match_v1.txt as it sits on disk.")
		template = PROMPT_FILE.read_text(encoding="utf-8")
		# version=0 (unregistered) signals "not yet promoted to MLflow" -- this lets prompt edits
		# be scored before prompt_registry.get_active_prompt() would auto-promote them on the next
		# live cycle. PROMPT_FILE is always job_match_v1.txt (legacy schema).
		return LoadedPrompt(version=PromptVersion(name=PROMPT_NAME, version=0, template=template), schema_mode="legacy", rubric_version=1)

	raise ValueError(f"Unknown prompt source: {source!r}")


def _criteria_in_range_fraction(
	predicted: dict[str, dict[str, Any]] | None, expected: dict[str, tuple[int, int]] | None
) -> float | None:
	"""Fraction of a case's expected_criteria bounds the predicted per-criterion scores actually
	landed in -- None when the case doesn't assert expected_criteria at all (most cases in the
	real golden_dataset_v2.jsonl, deliberately left unset rather than guessed -- see its
	generation notes), 0.0 if the prompt returned no breakdown to compare against (e.g. this
	case slipped through with a legacy prompt) but the case DID expect one.
	"""
	if not expected:
		return None
	if not predicted:
		return 0.0
	in_range = sum(1 for name, (lo, hi) in expected.items() if predicted.get(name) and lo <= predicted[name]["score"] <= hi)
	return in_range / len(expected)


def _row_from_score(case: EvalCase, score: Any) -> dict[str, Any]:
	predicted_is_match = score.is_match
	score_in_range = None
	if case.expected_score_min is not None:
		score_in_range = case.expected_score_min <= score.match_score <= case.expected_score_max

	return {
		"id": case.id,
		"expected_is_match": case.expected_is_match,
		"predicted_is_match": predicted_is_match,
		"correct": predicted_is_match == case.expected_is_match,
		"predicted_score": score.match_score,
		"expected_score_min": case.expected_score_min,
		"expected_score_max": case.expected_score_max,
		"score_in_range": score_in_range,
		"criteria_in_range": _criteria_in_range_fraction(score.score_breakdown, case.expected_criteria),
		"reasoning": score.reasoning,
		"prompt_tokens": score.token_usage.prompt_tokens,
		"completion_tokens": score.token_usage.completion_tokens,
		"total_tokens": score.token_usage.total_tokens,
		"error": None,
	}


def _run_one_case(
	*,
	case: EvalCase,
	default_resume: str,
	loaded_prompt: LoadedPrompt,
	llm_client: Any,
	llm_model: str,
	provider: str,
	threshold: int,
) -> dict[str, Any]:
	resume_text = case.resume if case.resume is not None else default_resume
	score = score_job(
		client=llm_client,
		model=llm_model,
		provider=provider,
		loaded_prompt=loaded_prompt,
		resume=resume_text,
		job=case.job,
		threshold=threshold,
		bucket="eval",
	)
	return _row_from_score(case, score)


def _run_batch_of_cases(
	*,
	cases: list[EvalCase],
	default_resume: str,
	loaded_prompt: LoadedPrompt,
	llm_client: Any,
	llm_model: str,
	provider: str,
	threshold: int,
) -> list[dict[str, Any]]:
	"""Scores a chunk of cases in one score_jobs_batch() call -- exercises the exact batch
	scoring path backfill/processes/rescore_with_prompt.py uses in production, so a batch-mode
	eval run is also a correctness check on it before trusting it against real data.

	Eval cases have no real job_id; this assigns synthetic 1-indexed ids purely to correlate the
	batch response back to cases within this chunk -- never persisted anywhere. A case with a
	per-case resume override can't share the main batch call (score_jobs_batch scores one resume
	against many jobs), so it's scored alone via a batch-of-one against its own resume instead.

	Unlike _run_one_case (wrapped per-case by the caller's try/except), a failure here fails the
	whole chunk -- an inherent trade-off of batching, same as it is for the real backfill process.
	"""
	rows: list[dict[str, Any]] = []
	batchable = [case for case in cases if case.resume is None]
	overridden = [case for case in cases if case.resume is not None]

	if batchable:
		jobs = [(index, case.job) for index, case in enumerate(batchable, start=1)]
		scores = score_jobs_batch(
			client=llm_client,
			model=llm_model,
			provider=provider,
			loaded_prompt=loaded_prompt,
			resume=default_resume,
			jobs=jobs,
			threshold=threshold,
			bucket="eval",
		)
		for index, case in enumerate(batchable, start=1):
			score = scores.get(index)
			rows.append(_row_from_score(case, score) if score is not None else _error_row(case, "excluded_from_batch_response"))

	for case in overridden:
		scores = score_jobs_batch(
			client=llm_client,
			model=llm_model,
			provider=provider,
			loaded_prompt=loaded_prompt,
			resume=case.resume,
			jobs=[(1, case.job)],
			threshold=threshold,
			bucket="eval",
		)
		score = scores.get(1)
		rows.append(_row_from_score(case, score) if score is not None else _error_row(case, "excluded_from_batch_response"))

	return rows


def _error_row(case: EvalCase, error_message: str) -> dict[str, Any]:
	# No token counts -- a case that errors out (rate-limited, unparseable response, ...) never
	# reached the point where evaluate_match() had a successful response to read usage off of, so
	# there's nothing honest to report here (0 would misleadingly claim a free call).
	return {
		"id": case.id,
		"expected_is_match": case.expected_is_match,
		"predicted_is_match": None,
		"correct": None,
		"predicted_score": None,
		"expected_score_min": case.expected_score_min,
		"expected_score_max": case.expected_score_max,
		"score_in_range": None,
		"criteria_in_range": None,
		"reasoning": "",
		"prompt_tokens": None,
		"completion_tokens": None,
		"total_tokens": None,
		"error": error_message,
	}


ROW_COLUMNS = (
	"id",
	"expected_is_match",
	"predicted_is_match",
	"correct",
	"predicted_score",
	"expected_score_min",
	"expected_score_max",
	"score_in_range",
	"criteria_in_range",
	"reasoning",
	"prompt_tokens",
	"completion_tokens",
	"total_tokens",
	"error",
)


def _rows_to_columns(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
	"""mlflow.log_table expects column-oriented data ({col: [values...]}), not the row-oriented
	list our loop naturally builds -- convert here rather than shaping the loop around it."""
	return {column: [row.get(column) for row in rows] for column in ROW_COLUMNS}


def _compute_summary(rows: list[dict[str, Any]], *, total_cases: int) -> dict[str, Any]:
	scored = [row for row in rows if row["error"] is None]
	errored_count = len(rows) - len(scored)

	tp = sum(1 for row in scored if row["predicted_is_match"] and row["expected_is_match"])
	fp = sum(1 for row in scored if row["predicted_is_match"] and not row["expected_is_match"])
	fn = sum(1 for row in scored if not row["predicted_is_match"] and row["expected_is_match"])
	tn = sum(1 for row in scored if not row["predicted_is_match"] and not row["expected_is_match"])

	accuracy = (tp + tn) / len(scored) if scored else None
	precision = tp / (tp + fp) if (tp + fp) > 0 else None
	recall = tp / (tp + fn) if (tp + fn) > 0 else None
	f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None

	ranged = [row for row in scored if row["score_in_range"] is not None]
	score_in_range_rate = (sum(1 for row in ranged if row["score_in_range"]) / len(ranged)) if ranged else None

	# Only meaningful for cases that assert expected_criteria (schema_mode "single"/"batch"
	# prompts, e.g. job_match_v4/v5) -- None (not 0) when no case in this run asserted any, same
	# "absent means not applicable" convention as score_in_range_rate above.
	criteria_ranged = [row for row in scored if row["criteria_in_range"] is not None]
	criteria_in_range_rate = (
		(sum(row["criteria_in_range"] for row in criteria_ranged) / len(criteria_ranged)) if criteria_ranged else None
	)

	mean_predicted_score = (sum(row["predicted_score"] for row in scored) / len(scored)) if scored else None

	total_prompt_tokens = sum(row["prompt_tokens"] for row in scored)
	total_completion_tokens = sum(row["completion_tokens"] for row in scored)
	total_tokens = sum(row["total_tokens"] for row in scored)
	mean_tokens_per_case = (total_tokens / len(scored)) if scored else None

	summary: dict[str, Any] = {
		"total_cases": total_cases,
		"evaluated_cases": len(scored),
		"errored_cases": errored_count,
		"true_positive": tp,
		"false_positive": fp,
		"false_negative": fn,
		"true_negative": tn,
		# Total LLM token consumption for this run -- summed over only the cases that actually got
		# a scored response (see _error_row's comment on why errored cases contribute nothing).
		"total_prompt_tokens": total_prompt_tokens,
		"total_completion_tokens": total_completion_tokens,
		"total_tokens": total_tokens,
	}
	if accuracy is not None:
		summary["accuracy"] = accuracy
	if precision is not None:
		summary["precision"] = precision
	if recall is not None:
		summary["recall"] = recall
	if f1 is not None:
		summary["f1"] = f1
	if score_in_range_rate is not None:
		summary["score_in_range_rate"] = score_in_range_rate
	if criteria_in_range_rate is not None:
		summary["criteria_in_range_rate"] = criteria_in_range_rate
	if mean_predicted_score is not None:
		summary["mean_predicted_score"] = mean_predicted_score
	if mean_tokens_per_case is not None:
		summary["mean_tokens_per_case"] = mean_tokens_per_case
	return summary


def run_offline_eval(
	*,
	eval_id: str | None = None,
	dataset_path: Path,
	prompt_source: str,
	prompt_version: int | None = None,
	provider: str | None,
	model: str | None,
	threshold: int | None,
	experiment_name: str | None,
	run_name: str | None,
	limit: int | None,
	sweep_id: str | None = None,
	batch_size: int | None = None,
) -> dict[str, Any]:
	eval_id = eval_id or new_id()
	log = LOGGER.bind(eval_id=eval_id)

	ensure_tracking_uri_configured()
	resolved_experiment_name = experiment_name or load_mlflow_eval_experiment_name()
	set_experiment_safely(resolved_experiment_name)
	log.action("mlflow_target", tracking_uri=get_tracking_uri(), experiment_name=resolved_experiment_name)

	rows: list[dict[str, Any]] = []
	# The MLflow run wraps setup (dataset/prompt loading, client construction) as well as the
	# scoring loop, not just the loop -- that way a run is the single durable record of an eval
	# from the moment it's triggered, including setup failures (bad dataset, missing prompt, ...).
	# mlflow.start_run()'s context manager marks the run FAILED and re-raises automatically on any
	# exception escaping this block; the `except Exception` below only attaches a human-readable
	# error_message tag before letting that happen, since MLflow doesn't record the exception text
	# itself -- api/eval_runs.py reads that tag back to answer "why did this run fail?" instead of
	# tracking it in process memory.
	with mlflow.start_run(run_name=run_name or f"eval-{eval_id}"):
		run = mlflow.active_run()
		run_id = run.info.run_id if run is not None else None
		if run_id is not None:
			log.action("mlflow_run_started", run_id=run_id)
		tags = {
			"eval_id": eval_id,
			"run_type": "offline_eval",
			"prompt_name": PROMPT_NAME,
			"prompt_source": prompt_source,
			"dataset_path": str(dataset_path),
		}
		if sweep_id:
			# Present only for runs triggered by POST /evals/sweep -- lets api/eval_runs.py group
			# every version's run back together for side-by-side comparison in GET /evals.
			tags["sweep_id"] = sweep_id
		mlflow.set_tags(tags)
		try:
			cases = load_golden_dataset(dataset_path)
			if limit is not None:
				cases = cases[:limit]
			log.action("dataset_loaded", dataset=str(dataset_path), case_count=len(cases))

			default_resume = load_resume()
			loaded_prompt = _load_prompt_version(prompt_source, prompt_version)
			# "local" (not "0") is the human-readable tag/param value for the unregistered
			# on-disk prompt -- version_id would technically read "0" (PromptVersion's
			# placeholder for "not yet registered"), which is correct but far less legible in
			# the MLflow UI's run list.
			resolved_prompt_version = "local" if prompt_source == "local" else loaded_prompt.version_id
			resolved_batch_size = batch_size or load_backfill_batch_size()
			resolved_provider = provider or load_provider_name()
			resolved_model = model or load_model_name(resolved_provider)
			resolved_threshold = threshold if threshold is not None else load_match_threshold()
			llm_client = build_client(resolved_provider)
		except Exception as error:
			message = f"Invalid golden dataset: {error}" if isinstance(error, DatasetError) else str(error)
			mlflow.set_tag("error_message", message)
			raise

		with mlflow.start_span(
			name="offline_eval",
			span_type="EVALUATOR",
			attributes={
				"eval_id": eval_id,
				"prompt_source": prompt_source,
				"llm_provider": resolved_provider,
				"llm_model": resolved_model,
			},
			run_id=run_id,
		) as eval_span:
			try:
				eval_span.set_inputs(
					{
						"dataset_path": str(dataset_path),
						"dataset_case_count": len(cases),
						"match_threshold": resolved_threshold,
					}
				)
				mlflow.set_tag("llm_provider", resolved_provider)
				mlflow.set_tag("prompt_schema_mode", loaded_prompt.schema_mode)
				params = {
					"prompt_version": resolved_prompt_version,
					"prompt_schema_mode": loaded_prompt.schema_mode,
					"llm_provider": resolved_provider,
					"llm_model": resolved_model,
					"match_threshold": resolved_threshold,
					"dataset_case_count": len(cases),
				}
				if limit is not None:
					params["limit"] = limit
				if loaded_prompt.schema_mode == "batch":
					params["batch_size"] = resolved_batch_size
				mlflow.log_params(params)
				mlflow.log_artifact(str(dataset_path))

				if loaded_prompt.schema_mode == "batch":
					# One span per chunk (not per case) -- score_jobs_batch makes one LLM call for
					# the whole chunk, so a per-case span would misleadingly suggest per-case
					# isolation the underlying call doesn't have. A chunk that raises fails every
					# case in it as an error row rather than aborting the whole run, so one bad
					# chunk doesn't cost the rest of the dataset.
					chunks = [cases[i : i + resolved_batch_size] for i in range(0, len(cases), resolved_batch_size)]
					for chunk in chunks:
						chunk_log = log.bind(chunk_case_ids=[case.id for case in chunk])
						try:
							with mlflow.start_span(
								name="eval_batch",
								span_type="TASK",
								attributes={"case_ids": [case.id for case in chunk]},
							) as batch_span:
								batch_span.set_inputs({"case_count": len(chunk)})
								batch_rows = _run_batch_of_cases(
									cases=chunk,
									default_resume=default_resume,
									loaded_prompt=loaded_prompt,
									llm_client=llm_client,
									llm_model=resolved_model,
									provider=resolved_provider,
									threshold=resolved_threshold,
								)
								batch_span.set_outputs(
									{"correct_count": sum(1 for row in batch_rows if row["correct"])}
								)
							chunk_log.action("chunk_scored", case_count=len(chunk))
							rows.extend(batch_rows)
						except RateLimitError as error:
							chunk_log.action("chunk_rate_limited", error=str(error), retry_after=error.retry_after)
							rows.extend(_error_row(case, "rate_limited") for case in chunk)
						except (MatchResponseError, TransientProviderError) as error:
							chunk_log.action("chunk_errored", error=str(error))
							rows.extend(_error_row(case, str(error)) for case in chunk)
						except GuardrailBlockedError as error:
							chunk_log.action("chunk_guardrail_blocked", guardrail=error.guardrail, error=str(error))
							rows.extend(_error_row(case, f"guardrail_blocked:{error.guardrail}: {error}") for case in chunk)
				else:
					for case in cases:
						case_log = log.bind(case_id=case.id)

						try:
							with mlflow.start_span(
								name="eval_case",
								span_type="TASK",
								attributes={"case_id": case.id},
							) as case_span:
								case_span.set_inputs(
									{
										"expected_is_match": case.expected_is_match,
										"expected_score_min": case.expected_score_min,
										"expected_score_max": case.expected_score_max,
									}
								)
								row = _run_one_case(
									case=case,
									default_resume=default_resume,
									loaded_prompt=loaded_prompt,
									llm_client=llm_client,
									llm_model=resolved_model,
									provider=resolved_provider,
									threshold=resolved_threshold,
								)
								case_span.set_outputs(
									{
										"predicted_is_match": row["predicted_is_match"],
										"predicted_score": row["predicted_score"],
										"correct": row["correct"],
									}
								)
							case_log.action(
								"case_scored",
								predicted_score=row["predicted_score"],
								correct=row["correct"],
							)
							rows.append(row)
						except RateLimitError as error:
							# score_job() already retries a rate limit with backoff before raising, so
							# reaching here means retries are exhausted for this case specifically --
							# same "skip and move on" response as the live/backfill cycle, not aborting
							# the rest of the dataset over one case.
							case_log.action("case_rate_limited", error=str(error), retry_after=error.retry_after)
							rows.append(_error_row(case, "rate_limited"))
						except (MatchResponseError, TransientProviderError) as error:
							case_log.action("case_errored", error=str(error))
							rows.append(_error_row(case, str(error)))
						except GuardrailBlockedError as error:
							case_log.action("case_guardrail_blocked", guardrail=error.guardrail, error=str(error))
							rows.append(_error_row(case, f"guardrail_blocked:{error.guardrail}: {error}"))

				summary = _compute_summary(rows, total_cases=len(cases))
				mlflow.log_metrics({key: value for key, value in summary.items() if isinstance(value, (int, float))})
				mlflow.log_table(data=_rows_to_columns(rows), artifact_file="eval_results.json")
				eval_span.set_outputs(summary)
				# Persisted as a run tag (not just logged) so api/eval_runs.py can read it back later
				# to link out to this run's trace in the MLflow UI -- the span object itself only
				# lives for the duration of this process.
				mlflow.set_tag("trace_id", eval_span.trace_id)
				log.action("mlflow_trace_ready", trace_id=eval_span.trace_id)
			except Exception as error:
				mlflow.set_tag("error_message", str(error))
				raise

	# Traces are exported asynchronously; force a flush in short-lived eval runs.
	mlflow.flush_trace_async_logging(terminate=False)

	log.action("eval_complete", **summary)
	return summary


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run the offline eval harness against a golden dataset.")
	parser.add_argument("--dataset", required=True, type=Path, help="Path to a golden-dataset JSONL file.")
	parser.add_argument(
		"--prompt-source",
		choices=("production", "local"),
		default="production",
		help="'production' loads the MLflow-registered prompt at the 'production' alias (read-only). "
		"'local' renders prompts/job_match_v1.txt directly, without registering it, so you can eval "
		"an edit before it gets promoted by the next live cycle.",
	)
	parser.add_argument(
		"--prompt-version",
		type=int,
		default=None,
		help="With --prompt-source production, pins a specific registered version of the prompt "
		"(e.g. 3) instead of whichever version the 'production' alias currently points to -- run "
		"the same dataset against several versions to compare how the prompt's behavior has "
		"drifted over time. Not valid with --prompt-source local.",
	)
	parser.add_argument(
		"--provider", choices=("gemini",), default=None, help="Overrides LLM_PROVIDER for this run."
	)
	parser.add_argument("--model", default=None, help="Overrides the active provider's model env var for this run.")
	parser.add_argument("--threshold", type=int, default=None, help="Overrides MATCH_THRESHOLD for this run.")
	parser.add_argument("--experiment-name", default=None, help="Overrides MLFLOW_EVAL_EXPERIMENT_NAME.")
	parser.add_argument("--run-name", default=None, help="MLflow run name; defaults to eval-<eval_id>.")
	parser.add_argument("--limit", type=int, default=None, help="Only score the first N cases (smoke testing).")
	parser.add_argument(
		"--batch-size",
		type=int,
		default=None,
		help="Only applies when the resolved prompt has schema_mode='batch' (e.g. job_match_v5.txt): "
		"how many cases go into one score_jobs_batch() call. Defaults to BACKFILL_BATCH_SIZE, the "
		"same default the real backfill process uses. Ignored for schema_mode='single'/'legacy' "
		"prompts, which always score one case per call.",
	)
	return parser.parse_args()


def main() -> None:
	args = _parse_args()
	try:
		summary = run_offline_eval(
			dataset_path=args.dataset,
			prompt_source=args.prompt_source,
			prompt_version=args.prompt_version,
			provider=args.provider,
			model=args.model,
			threshold=args.threshold,
			experiment_name=args.experiment_name,
			run_name=args.run_name,
			limit=args.limit,
			batch_size=args.batch_size,
		)
	except DatasetError as error:
		raise SystemExit(f"Invalid golden dataset: {error}") from error

	print("\nOffline eval summary:")
	for key, value in summary.items():
		print(f"  {key}: {value}")


if __name__ == "__main__":
	main()
