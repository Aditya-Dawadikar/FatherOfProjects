from __future__ import annotations

import logging
from pathlib import Path

import mlflow
from mlflow.entities.model_registry.prompt_version import PromptVersion

from mlflow_utils import ensure_tracking_uri_configured


LOGGER = logging.getLogger(__name__)

PROMPT_NAME = "job_match_prompt"
PROMPT_ALIAS = "production"
PROMPT_FILE = Path(__file__).with_name("prompts") / "job_match_v1.txt"


def get_active_prompt() -> PromptVersion:
	"""Load the current 'production' version of the job-match prompt, registering a new
	version in MLflow (and re-pointing the alias) if prompts/job_match_v1.txt changed since
	the last registered version.
	"""
	ensure_tracking_uri_configured()

	file_template = PROMPT_FILE.read_text(encoding="utf-8")

	current = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@{PROMPT_ALIAS}", allow_missing=True)
	if current is not None and current.template == file_template:
		return current

	LOGGER.info("Registering new prompt version for %s (file content changed or first run)", PROMPT_NAME)
	new_version = mlflow.genai.register_prompt(
		name=PROMPT_NAME,
		template=file_template,
		commit_message="Synced from prompts/job_match_v1.txt",
	)
	mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias=PROMPT_ALIAS, version=new_version.version)
	LOGGER.info("Prompt %s now at version %s (alias=%s)", PROMPT_NAME, new_version.version, PROMPT_ALIAS)
	return new_version
