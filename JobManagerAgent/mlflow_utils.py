from __future__ import annotations

import mlflow

from env_utils import load_env_value


_tracking_uri_configured = False


def ensure_tracking_uri_configured() -> None:
	"""Point the mlflow client at MLFLOW_TRACKING_URI, once per process.

	Shared by prompt_registry.py (prompt versioning) and matcher.py (experiment
	tracking) so both talk to the same MLflow Tracking Server without racing to
	set the URI twice.
	"""
	global _tracking_uri_configured
	if _tracking_uri_configured:
		return
	tracking_uri = load_env_value("MLFLOW_TRACKING_URI", "sqlite:///./mlflow.db")
	mlflow.set_tracking_uri(tracking_uri)
	_tracking_uri_configured = True


def load_mlflow_experiment_name() -> str:
	return load_env_value("MLFLOW_EXPERIMENT_NAME", "job_matching")


def load_mlflow_eval_experiment_name() -> str:
	"""Separate experiment from the live-cycle one: eval runs log accuracy/precision/recall
	against a golden dataset, a different metric shape than live per-cycle counts, so keeping
	them apart avoids mixing incomparable runs in the same MLflow comparison table."""
	return load_env_value("MLFLOW_EVAL_EXPERIMENT_NAME", "job_matching_evals")
