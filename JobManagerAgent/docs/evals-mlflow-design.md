# JobManagerAgent Evals and MLflow Design

## Purpose

The eval and MLflow layer exists to make JobManagerAgent measurable. It answers three questions:

1. Did the current prompt and model produce good job matches?
2. Did a change make matching better or worse?
3. What happened during a specific live cycle or offline eval run, and how can we trace it back to the logs and database?

This document covers the live matching flow, the offline golden-dataset eval harness, prompt versioning, and everything that is written to MLflow.

## Scope

The design covers:

- live matching cycles in [../matcher.py](../matcher.py)
- offline eval runs in [../evals/run_offline_eval.py](../evals/run_offline_eval.py)
- shared MLflow configuration in [../mlflow_utils.py](../mlflow_utils.py)
- prompt registration and aliasing in [../prompt_registry.py](../prompt_registry.py)

## Why this matters

MLflow is the canonical place for experiment history and regression analysis. Without it, the system can still score jobs and write results to Postgres, but it becomes much harder to:

- compare prompt edits over time
- compare providers or model swaps fairly
- detect regressions before they affect production traffic
- explain what happened during a specific cycle
- correlate results with Redis events, logs, and stored match rows

## High-level model

The system uses two different MLflow patterns:

- Live-cycle tracking: one run per matching cycle, used for operational visibility and prompt/model comparison.
- Offline eval tracking: one run per golden-dataset evaluation, used to validate a prompt or model before it is used in production.

These are intentionally separated into different experiments so live-cycle metrics do not get mixed with evaluation metrics.

## What is tracked in MLflow

### 1. Prompt versioning

Prompt versions are registered in MLflow through the prompt registry workflow.

What is logged:

- prompt name and prompt version as MLflow parameters
- the production alias relationship in the prompt registry layer

Why it matters:

- every match result can be tied to the exact prompt version that produced it
- prompt edits can be compared without guessing which template was active
- regressions can be attributed to a specific prompt change rather than a vague "it changed"

### 2. Provider and model configuration

For both live cycles and eval runs, the active provider and model are recorded.

What is logged:

- llm_provider as a parameter and tag
- llm_model as a parameter

Why it matters:

- a provider swap or model update becomes visible in MLflow history
- evaluations remain comparable even when the underlying backend changes
- operational issues can be tied to a specific provider/model combination

### 3. Live matching-cycle runs

Each call to the matching cycle starts a new MLflow run.

What is logged:

- Parameters
  - prompt_version
  - llm_provider
  - llm_model
  - match_threshold
  - max_jobs_per_cycle
  - llm_request_delay_seconds
- Tags
  - cycle_id
  - prompt_name
  - llm_provider
- Metrics
  - candidate_count
  - evaluated_count
  - matched_count
  - failed_count
  - not_found_count
  - rate_limited
- Per-job metrics
  - match_score
  - is_match
  - logged with the job index as the MLflow step so the run can show score progression over the cycle

Why it matters:

- each cycle becomes a first-class experiment record
- the run can show how many jobs were considered, how many were scored, and how many matched
- per-job metrics make it possible to inspect whether a run degraded mid-cycle or whether the quality profile changed across the batch

### 4. Offline eval runs

Offline eval runs are separate from the live matching cycles and use a golden dataset instead of live crawled jobs.

What is logged:

- Parameters
  - prompt_version
  - llm_provider
  - llm_model
  - match_threshold
  - dataset_case_count
- Tags
  - eval_id
  - run_type
  - prompt_name
  - prompt_source
  - llm_provider
  - dataset_path
- Summary metrics
  - total_cases
  - evaluated_cases
  - errored_cases
  - true_positive
  - false_positive
  - false_negative
  - true_negative
  - accuracy
  - precision
  - recall
  - f1
  - score_in_range_rate
  - mean_predicted_score
- A structured table artifact containing one row per eval case
- The dataset artifact itself, so an eval run is self-contained

Why it matters:

- prompt or model changes can be validated before they affect production traffic
- eval runs provide a stable benchmark for regression detection
- the per-case table makes it easy to inspect surprising predictions and failure modes

### 5. Traces and spans

Both the live and offline flows create MLflow tracing spans.

Current span structure:

- live matching cycle span: matching_cycle
- per-job span: evaluate_job
- offline eval span: offline_eval
- per-case span: eval_case

What is captured:

- span inputs such as cycle id, job url, expected match flags, and threshold
- span outputs such as the final status or evaluation summary
- trace IDs that can be correlated with logs

Why it matters:

- traces make it easier to understand where a run failed or degraded
- they give a path from the run to the underlying operation without needing to inspect every log line manually

## Data flow

### Live matching flow

1. The matching cycle loads the active prompt and model configuration.
2. It starts an MLflow run and records run metadata.
3. For each evaluated job, it logs per-job metrics with the current step.
4. At the end of the cycle, it logs aggregate metrics and closes the run.

### Offline eval flow

1. The eval harness loads a golden dataset and the active prompt/model configuration.
2. It starts an MLflow run for the eval.
3. Each case is scored and logged as a row in the eval result table.
4. Summary metrics are logged and the dataset plus result table are stored as artifacts.

## Evals lifecycle: exact sequence when the agent acts

This section describes the full lifecycle from the moment the agent decides to act until the instrumentation is finalized.

### 1. Agent startup and environment setup

When the agent process starts, it initializes logging, loads environment configuration, and ensures the MLflow tracking URI is configured.

Instrumentation captured:

- MLflow tracking URI is validated and configured once per process.
- The configured experiment name is resolved.
- The agent logs startup metadata such as the tracking URI and experiment name.

Why it matters:

- if the tracking URI is invalid, the run never reaches MLflow logging successfully.
- this is the first point where the system establishes the destination for all later eval artifacts.

### 2. Prompt resolution and version selection

Before the agent evaluates any jobs, it resolves the active prompt.

Instrumentation captured:

- the prompt version is resolved from the registered MLflow prompt version or from the local file when running an offline eval
- the resolved prompt version is passed into the run as a parameter

Why it matters:

- this makes each run attributable to a specific prompt revision.
- it enables prompt-by-prompt comparison in MLflow.

### 3. Run creation

Once the evaluation loop begins, the agent creates an MLflow run.

Instrumentation captured:

- a new run is started with a run name such as cycle-<id> or eval-<id>
- the run id is recorded in the logs
- tags and parameters are set for the run

Typical run-level fields:

- cycle_id or eval_id
- prompt_name
- prompt_version
- llm_provider
- llm_model
- match_threshold
- dataset_case_count or max_jobs_per_cycle

Why it matters:

- this is the root object for the entire lifecycle.
- every later metric, span, and artifact attaches to this run.

### 4. Span creation for the overall workflow

A parent span is created around the whole operation.

Instrumentation captured:

- a workflow span such as matching_cycle or offline_eval
- span inputs such as cycle id, job selection limit, threshold, or dataset properties
- span outputs such as the final summary or cycle result

Why it matters:

- it gives a structured trace of the top-level action.
- it enables tracking of the workflow as a single unit rather than as unrelated log lines.

### 5. Per-item evaluation

Each job or eval case is evaluated independently.

Instrumentation captured:

- a child span for each item: evaluate_job for live jobs, eval_case for offline cases
- the job or case identifier as span attributes
- inputs such as the URL, role, company, expected match flag, or threshold
- outputs such as predicted score, predicted match flag, and correctness

Why it matters:

- this is where the actual model decision becomes observable.
- individual failures, retries, or bad predictions become attributable to a specific item rather than the whole run.

### 6. Metric emission

As each item finishes, the agent emits metrics.

Instrumentation captured:

- per-item metrics for live runs:
  - match_score
  - is_match
- run-level aggregates for live runs:
  - candidate_count
  - evaluated_count
  - matched_count
  - failed_count
  - not_found_count
  - rate_limited
- summary metrics for eval runs:
  - accuracy
  - precision
  - recall
  - f1
  - true/false positives and negatives
  - score range rate

Why it matters:

- this is what makes the experiment comparable across runs.
- it turns the system from a one-off decision engine into a measurable workflow.

### 7. Artifact logging

For offline evals, the run also stores artifacts.

Instrumentation captured:

- the dataset file itself
- a structured table artifact with one row per eval case
- optional result summaries

Why it matters:

- later analysis does not depend on the original local file still existing.
- the run becomes self-contained and reproducible.

### 8. Completion and flush

When the run finishes, the agent finalizes the instrumentation.

Instrumentation captured:

- final run summary is logged
- traces are flushed so that short-lived runs do not lose their data on shutdown
- completion events are emitted to the application logs and Redis stream

Why it matters:

- this is the point where the lifecycle becomes durable and queryable in MLflow.
- it prevents silent loss of traces or metrics when the process exits quickly.

## Design decisions

### Separate experiment namespaces

Live matching runs and offline evals use different experiment names. This prevents the comparison views from being polluted by incompatible metric shapes.

### Structured metadata over raw payloads

The current design intentionally logs structured parameters, metrics, and artifacts rather than dumping large prompt or job payloads into MLflow. This keeps the tracking system practical and readable while still preserving the information needed for comparison and debugging.

### Correlation with operational systems

Each run carries identifiers that can be correlated with the rest of the system:

- cycle_id for live matching cycles
- eval_id for offline eval runs
- prompt version and model/provider values for cross-run comparison

This makes it easier to connect MLflow history to Redis stream events, logs, and database rows.

## Operational guidance

To make the MLflow setup useful in practice:

- ensure the tracking URI points to a remote MLflow server rather than a local sqlite file
- keep the experiment names stable so dashboards and comparisons remain meaningful
- use the same prompt version and provider/model combination when comparing runs
- review both aggregate metrics and the per-case result table when investigating regressions

## Summary

The MLflow integration is not just telemetry. It is the primary mechanism for understanding whether the agent is getting better or worse over time. It turns prompt edits, model swaps, and matching cycles into comparable experiment records that can be reviewed, compared, and debugged.
