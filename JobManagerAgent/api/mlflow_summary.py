from __future__ import annotations

from datetime import datetime, timezone

import mlflow
from fastapi import APIRouter
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from pydantic import BaseModel

from integrations.mlflow import PROMPT_NAME, get_active_prompt
from shared.job_data import get_shared_engine
from utils.mlflow_utils import (
    build_mlflow_experiment_url,
    ensure_tracking_uri_configured,
    get_mlflow_ui_base_url,
    load_mlflow_eval_experiment_name,
    load_mlflow_experiment_name,
    load_mlflow_guardrails_eval_experiment_name,
    load_mlflow_tool_eval_experiment_name,
)


router = APIRouter(prefix="/mlflow-summary", tags=["mlflow-summary"])

# Bounds every count/sum below to the N most recent runs per experiment rather than the true
# unbounded total -- cheap enough for an Overview-page card to fetch on every load, at the cost of
# undercounting past this many runs in any single experiment (acceptable for a KPI headline, unlike
# the exact-accounting needs of api/eval_runs.py's per-run listing endpoints).
_MAX_RUNS_PER_EXPERIMENT = 20_000


class EvalTypeCount(BaseModel):
    label: str
    experiment_name: str
    run_count: int
    mlflow_url: str | None


class MlflowSummaryResponse(BaseModel):
    generated_at: str
    mlflow_base_url: str | None
    traces_collected: int
    traces_mlflow_url: str | None
    offline_evals_triggered: int
    offline_evals_by_type: list[EvalTypeCount]
    registered_prompt_versions: int
    production_prompt_version: str | None
    total_tokens_tracked: int
    total_cost_usd_tracked: float


def _experiment_runs(experiment_name: str) -> tuple[str | None, list]:
    """(experiment_id, runs) for experiment_name, or (None, []) if it doesn't exist yet (e.g.
    nothing has triggered that eval type/the live agent hasn't started a cycle in this environment
    yet) -- a summary card should read as "0 so far", not throw a 500."""
    ensure_tracking_uri_configured()
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        return None, []
    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        max_results=_MAX_RUNS_PER_EXPERIMENT,
        order_by=["attributes.start_time DESC"],
        output_format="list",
    )
    return experiment.experiment_id, runs


def _sum_metric(runs: list, metric_key: str) -> float:
    return sum(run.data.metrics[metric_key] for run in runs if metric_key in run.data.metrics)


def _load_prompt_registry_stats() -> tuple[int, str | None]:
    """(registered version count, current production version) -- degrades to (0, None) instead of
    raising if MLflow is briefly unreachable, same fallback contract as agent_topology.py's
    _load_scoring_prompt()."""
    try:
        ensure_tracking_uri_configured()
        version_count = len(MlflowClient().search_prompt_versions(PROMPT_NAME))
    except MlflowException:
        version_count = 0

    try:
        production_version = get_active_prompt(get_shared_engine()).version_id
    except Exception:
        production_version = None

    return version_count, production_version


@router.get("", summary="Agent-observability KPIs rolled up from MLflow, for the dashboard Overview page")
def get_mlflow_summary() -> MlflowSummaryResponse:
    live_experiment_id, live_runs = _experiment_runs(load_mlflow_experiment_name())
    eval_experiment_id, eval_runs = _experiment_runs(load_mlflow_eval_experiment_name())
    tool_experiment_id, tool_eval_runs = _experiment_runs(load_mlflow_tool_eval_experiment_name())
    guardrails_experiment_id, guardrails_eval_runs = _experiment_runs(load_mlflow_guardrails_eval_experiment_name())

    offline_evals_by_type = [
        EvalTypeCount(
            label="Prompt Evals",
            experiment_name=load_mlflow_eval_experiment_name(),
            run_count=len(eval_runs),
            mlflow_url=build_mlflow_experiment_url(eval_experiment_id) if eval_experiment_id else None,
        ),
        EvalTypeCount(
            label="Tool-Selection Evals",
            experiment_name=load_mlflow_tool_eval_experiment_name(),
            run_count=len(tool_eval_runs),
            mlflow_url=build_mlflow_experiment_url(tool_experiment_id) if tool_experiment_id else None,
        ),
        EvalTypeCount(
            label="Guardrails Evals",
            experiment_name=load_mlflow_guardrails_eval_experiment_name(),
            run_count=len(guardrails_eval_runs),
            mlflow_url=build_mlflow_experiment_url(guardrails_experiment_id) if guardrails_experiment_id else None,
        ),
    ]

    registered_prompt_versions, production_prompt_version = _load_prompt_registry_stats()

    return MlflowSummaryResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        mlflow_base_url=get_mlflow_ui_base_url(),
        traces_collected=len(live_runs),
        traces_mlflow_url=build_mlflow_experiment_url(live_experiment_id) if live_experiment_id else None,
        offline_evals_triggered=sum(item.run_count for item in offline_evals_by_type),
        offline_evals_by_type=offline_evals_by_type,
        registered_prompt_versions=registered_prompt_versions,
        production_prompt_version=production_prompt_version,
        total_tokens_tracked=int(_sum_metric(eval_runs, "total_tokens")),
        total_cost_usd_tracked=round(_sum_metric(tool_eval_runs, "total_cost_usd"), 2),
    )
