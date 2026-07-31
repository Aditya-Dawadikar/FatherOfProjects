from __future__ import annotations

import logging

import mlflow
from mlflow import MlflowClient
from mlflow.entities.model_registry.prompt_version import PromptVersion
from mlflow.exceptions import MlflowException

from utils.config import PROMPT_ALIAS, PROMPT_FILE, PROMPT_NAME
from utils.mlflow_utils import ensure_tracking_uri_configured


LOGGER = logging.getLogger(__name__)


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


def register_prompt_variants() -> None:
	"""Registers every prompts/job_match_v*.txt file other than PROMPT_FILE (job_match_v1.txt,
	handled by get_active_prompt() above) as an additional version of PROMPT_NAME, skipping any
	whose exact template content is already registered.

	Called once at server startup (see api/app.py's lifespan) so a fresh Railway deploy has every
	variant file in prompts/ available in the MLflow prompt registry immediately -- without this,
	evals/run_offline_eval.py's --prompt-version would have nothing to pin against until someone
	registered them by hand. Idempotent (safe on every restart) and never touches the 'production'
	alias -- only get_active_prompt(), driven by job_match_v1.txt, moves that.
	"""
	ensure_tracking_uri_configured()
	variant_files = sorted(p for p in PROMPT_FILE.parent.glob("job_match_v*.txt") if p != PROMPT_FILE)
	if not variant_files:
		return

	client = MlflowClient()
	try:
		existing_templates = {version.template for version in client.search_prompt_versions(PROMPT_NAME)}
	except MlflowException as error:
		# The prompt name itself doesn't exist yet (e.g. this is the very first deploy and
		# get_active_prompt() hasn't run yet) -- nothing to dedupe against, so register everything.
		if error.error_code != "RESOURCE_DOES_NOT_EXIST":
			raise
		existing_templates = set()

	for path in variant_files:
		template = path.read_text(encoding="utf-8")
		if template in existing_templates:
			continue
		new_version = mlflow.genai.register_prompt(
			name=PROMPT_NAME,
			template=template,
			commit_message=f"Synced from {path.name}",
		)
		existing_templates.add(template)
		LOGGER.info("Registered prompt variant %s as %s version %s", path.name, PROMPT_NAME, new_version.version)
