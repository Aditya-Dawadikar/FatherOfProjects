from __future__ import annotations

import logging

import mlflow
from mlflow.entities import LifecycleStage
from mlflow.tracking import MlflowClient

from .env_utils import load_env_value


_tracking_uri_configured = False
LOGGER = logging.getLogger(__name__)


def _is_sqlite_uri(uri: str) -> bool:
	value = uri.strip().lower()
	return value.startswith("sqlite:")


def ensure_tracking_uri_configured() -> None:
	"""Point the mlflow client at MLFLOW_TRACKING_URI, once per process.

	Shared by prompt_registry.py (prompt versioning) and react_agent.py (experiment
	tracking) so both talk to the same MLflow Tracking Server without racing to
	set the URI twice.
	"""
	global _tracking_uri_configured
	if _tracking_uri_configured:
		return
	tracking_uri = load_env_value("MLFLOW_TRACKING_URI")
	if _is_sqlite_uri(tracking_uri):
		raise ValueError(
			"MLFLOW_TRACKING_URI must point to a remote MLflow Tracking Server; sqlite URIs are disabled"
		)
	mlflow.set_tracking_uri(tracking_uri)
	LOGGER.info("MLflow tracking configured uri=%s", tracking_uri)
	_tracking_uri_configured = True


def get_tracking_uri() -> str:
	ensure_tracking_uri_configured()
	return mlflow.get_tracking_uri()


def set_experiment_safely(experiment_name: str) -> None:
	"""Like mlflow.set_experiment(), but tolerates an experiment that was soft-deleted (e.g. by
	hand in the MLflow UI) while this process was running, instead of raising.

	mlflow.set_experiment() only auto-creates a *missing* experiment -- a same-named one sitting
	in the "deleted" lifecycle stage makes it raise ("Cannot set a deleted experiment ... as the
	active experiment") instead of recovering, which otherwise takes down every live cycle and
	eval run with the same error until someone notices and restores/renames it by hand. Since the
	name is still taken by the deleted experiment, mlflow.set_experiment() can't just create a
	fresh one under it either -- restoring the existing one is the only always-available fix via
	the public client API (there's no "permanently delete" call to make room for a truly new one).
	"""
	client = MlflowClient()
	experiment = client.get_experiment_by_name(experiment_name)
	if experiment is not None and experiment.lifecycle_stage != LifecycleStage.ACTIVE:
		LOGGER.warning(
			"Experiment %r was deleted; restoring it so tracking can continue", experiment_name
		)
		client.restore_experiment(experiment.experiment_id)
	mlflow.set_experiment(experiment_name)


def load_mlflow_experiment_name() -> str:
	return load_env_value("MLFLOW_EXPERIMENT_NAME", "job_matching")


def load_mlflow_eval_experiment_name() -> str:
	"""Separate experiment from the live-cycle one: eval runs log accuracy/precision/recall
	against a golden dataset, a different metric shape than live per-cycle counts, so keeping
	them apart avoids mixing incomparable runs in the same MLflow comparison table."""
	return load_env_value("MLFLOW_EVAL_EXPERIMENT_NAME", "job_matching_evals")


def _load_mlflow_ui_base_url() -> str | None:
	"""Publicly reachable MLflow UI origin, or None if MLFLOW_UI_BASE_URL isn't set.

	Deliberately separate from MLFLOW_TRACKING_URI: in production that points at Railway's
	internal hostname (e.g. mlflowserver.railway.internal:5000), which the tracking client can
	reach but a user's browser can't -- MLFLOW_UI_BASE_URL is the publicly reachable address of
	the same server, for building links only.
	"""
	base_url = load_env_value("MLFLOW_UI_BASE_URL", "")
	if not base_url:
		return None
	base_url = base_url.strip().rstrip("/")
	if not base_url.startswith(("http://", "https://")):
		# A bare host (e.g. mlflow-production-621c.up.railway.app, easy to paste without the
		# scheme) makes the link relative -- the browser resolves it against the dashboard's own
		# origin instead of MLflow's, landing on a broken same-origin URL. Default to https since
		# every real deployment target here (Railway) serves over TLS.
		base_url = f"https://{base_url}"
	return base_url


def build_mlflow_run_url(experiment_id: str, run_id: str) -> str | None:
	"""Links out to a run in the MLflow UI, or None if MLFLOW_UI_BASE_URL isn't set."""
	base_url = _load_mlflow_ui_base_url()
	if base_url is None:
		return None
	return f"{base_url}/#/experiments/{experiment_id}/runs/{run_id}"


def build_mlflow_trace_url(experiment_id: str, trace_id: str) -> str | None:
	"""Links out to a run's trace (span timeline) in the MLflow UI, or None if either
	MLFLOW_UI_BASE_URL isn't set or the run has no trace_id tag (e.g. it predates run_offline_eval.py
	tagging trace_id onto the run)."""
	base_url = _load_mlflow_ui_base_url()
	if base_url is None:
		return None
	return f"{base_url}/#/experiments/{experiment_id}/traces?selectedEvaluationId={trace_id}"
