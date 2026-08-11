from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import mlflow
from mlflow import MlflowClient
from mlflow.entities.model_registry.prompt_version import PromptVersion
from mlflow.exceptions import MlflowException
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from utils.agent_logger import get_agent_logger
from utils.config import PROMPT_ALIAS, PROMPT_FILE, PROMPT_NAME
from utils.mlflow_utils import ensure_tracking_uri_configured

from .models import PromptActiveHistoryRecord


LOGGER = get_agent_logger(__name__)

# A prompt file with no .meta.json sidecar (job_match_v1/v2/v3.txt) is "legacy": the model
# decides match_score/reasoning directly, the original (pre-rubric) response shape.
DEFAULT_SCHEMA_MODE = "legacy"
DEFAULT_RUBRIC_VERSION = 1

# A prompt file with no entry in version_status.json defaults to "decommissioned" -- adding a new
# job_match_v*.txt without also marking it "live" there doesn't silently make it eligible for new
# sweep studies (see list_sweep_eligible_versions()).
DEFAULT_PROMPT_STATUS = "decommissioned"
_VERSION_STATUS_FILE = PROMPT_FILE.parent / "version_status.json"


@dataclass(frozen=True)
class PromptActiveHistoryEntry:
	"""One transition of the 'production' alias -- written by every path that can change it
	(the bootstrap in get_active_prompt(), and set_active_prompt_version()), so there is exactly
	one durable record of "how did production get to be what it is" regardless of which path
	caused a given change."""

	changed_at: str
	from_version: str | None
	to_version: str
	schema_mode: str
	rubric_version: int
	reason: str


def _record_history_entry(engine: Engine, entry: PromptActiveHistoryEntry) -> None:
	"""Durable (Postgres, not Redis) for the same reason backfill run history is: this process
	redeploys on every push, and "when did production last change, from what, to what" is exactly
	what an operator needs to see on the dashboard right after a deploy -- see
	docs/backfill-design.md's migration sequence. Postgres, not Redis, because this is audit
	history that needs to survive anything short of losing the database itself, not fast
	operational state.
	"""
	with Session(engine) as session:
		session.add(
			PromptActiveHistoryRecord(
				changed_at=datetime.fromisoformat(entry.changed_at),
				from_version=entry.from_version,
				to_version=entry.to_version,
				schema_mode=entry.schema_mode,
				rubric_version=entry.rubric_version,
				reason=entry.reason,
			)
		)
		session.commit()


def get_active_prompt_history(engine: Engine, limit: int = 50) -> list[PromptActiveHistoryEntry]:
	"""Most-recent-first record of every 'production' alias change -- the durable audit trail
	GET /admin/active-prompt/history and the dashboard's migration observability page read from.
	"""
	with Session(engine) as session:
		rows = session.scalars(
			select(PromptActiveHistoryRecord).order_by(PromptActiveHistoryRecord.changed_at.desc()).limit(limit)
		).all()
	return [
		PromptActiveHistoryEntry(
			changed_at=row.changed_at.isoformat(),
			from_version=row.from_version,
			to_version=row.to_version,
			schema_mode=row.schema_mode,
			rubric_version=row.rubric_version,
			reason=row.reason,
		)
		for row in rows
	]


@dataclass(frozen=True)
class LoadedPrompt:
	"""An MLflow PromptVersion bundled with the schema metadata read off its source file's
	.meta.json sidecar (see prompts/job_match_v4.meta.json, job_match_v5.meta.json).
	schema_mode tells llm_providers (render_prompt/score_job/score_jobs_batch) how to render
	the template and parse its response:
	  - "legacy" (v1-v3, no sidecar): one job, LLM-decided match_score + reasoning.
	  - "single" (v4): one job, LLM returns only raw per-criterion scores; match_score is
	    computed deterministically from them (see llm_providers.base.compute_match_result).
	  - "batch" (v5): N jobs per call, same per-criterion contract as "single", batched for
	    backfill throughput. Never valid as the live "production"-aliased prompt.
	"""

	version: PromptVersion
	schema_mode: str
	rubric_version: int

	@property
	def version_id(self) -> str:
		return str(self.version.version)


def _load_sidecar_metadata(prompt_file: Path) -> tuple[str, int]:
	meta_file = prompt_file.with_suffix(".meta.json")
	if not meta_file.exists():
		return DEFAULT_SCHEMA_MODE, DEFAULT_RUBRIC_VERSION
	data = json.loads(meta_file.read_text(encoding="utf-8"))
	return (
		str(data.get("schema_mode", DEFAULT_SCHEMA_MODE)),
		int(data.get("rubric_version", DEFAULT_RUBRIC_VERSION)),
	)


def _resolve_schema_mode(template: str) -> tuple[str, int]:
	"""Matches a loaded PromptVersion's template text back to its source prompts/job_match_v*.txt
	file -- MLflow's own version numbering doesn't correspond 1:1 with our file names, so schema
	metadata has to be looked up by content match, not by number. Falls back to "legacy" for a
	template that no longer matches any file on disk (e.g. a stale registered version whose file
	was since edited) -- safer than guessing rubric-shaped parsing for a response shape we can't
	actually confirm belongs to a rubric prompt.
	"""
	for path in sorted(PROMPT_FILE.parent.glob("job_match_v*.txt")):
		if path.read_text(encoding="utf-8") == template:
			return _load_sidecar_metadata(path)
	return DEFAULT_SCHEMA_MODE, DEFAULT_RUBRIC_VERSION


def _load_version_status() -> dict[str, str]:
	"""Reads prompts/version_status.json -- a hand-edited file mapping a prompt file's stem (e.g.
	"job_match_v4") to "live" or "decommissioned". This is the single source of truth for which
	versions may still be used in new sweep studies (list_sweep_eligible_versions()): retiring a
	version or promoting a new one is just editing this file and redeploying, no code change or
	migration required. Read fresh on every call rather than cached, same as the .meta.json
	sidecar loader below -- this is an infrequently-called admin/reporting path, not a hot one.
	"""
	if not _VERSION_STATUS_FILE.exists():
		return {}
	return json.loads(_VERSION_STATUS_FILE.read_text(encoding="utf-8"))


def _resolve_prompt_status(template: str) -> str:
	"""Same content-match lookup as _resolve_schema_mode, against version_status.json instead of
	a .meta.json sidecar. A template that doesn't match any file on disk falls back to
	"decommissioned" for the same reason _resolve_schema_mode falls back to "legacy": safer to
	exclude an unrecognized version from sweep eligibility than to guess it's still current.
	"""
	status_map = _load_version_status()
	for path in sorted(PROMPT_FILE.parent.glob("job_match_v*.txt")):
		if path.read_text(encoding="utf-8") == template:
			return status_map.get(path.stem, DEFAULT_PROMPT_STATUS)
	return DEFAULT_PROMPT_STATUS


def get_active_prompt(engine: Engine) -> LoadedPrompt:
	"""Load whatever prompt version is currently aliased 'production'.

	Bootstraps ONLY when nothing has ever been aliased yet (a brand-new prompt name/MLflow
	instance): registers prompts/job_match_v1.txt and aliases it, so a fresh deploy has
	*something* production-aliased without requiring a manual POST /admin/active-prompt call
	first. Once anything is aliased -- from this bootstrap, or from set_active_prompt_version()
	-- this function is purely read-only: it does not compare against job_match_v1.txt's on-disk
	content and never re-points the alias on its own.

	`engine` is only actually touched on that bootstrap path (to record the history entry) --
	required anyway rather than made optional, so every call site is explicit about where its DB
	connection comes from instead of this function silently reaching for a hidden global one.

	CORRECTNESS NOTE (this used to be a real bug): an earlier version of this function re-diffed
	the alias's current template against job_match_v1.txt's on-disk content on *every* call, and
	silently re-registered + re-pointed the alias whenever they didn't match. That meant an
	explicit set_active_prompt_version() promotion to v4 got silently reverted back to v1 on the
	very next live/backfill cycle -- as soon as anything else was aliased, v1.txt's on-disk
	content permanently stopped matching it, so every single call re-triggered the "changed"
	branch forever. set_active_prompt_version() (POST /admin/active-prompt) is now the only way
	to change what's active after first bootstrap; local iteration on job_match_v1.txt content no
	longer auto-promotes on the next cycle the way it originally did.
	"""
	ensure_tracking_uri_configured()

	current = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@{PROMPT_ALIAS}", allow_missing=True)
	if current is not None:
		schema_mode, rubric_version = _resolve_schema_mode(current.template)
		return LoadedPrompt(version=current, schema_mode=schema_mode, rubric_version=rubric_version)

	LOGGER.action("prompt_bootstrap_registering", prompt_name=PROMPT_NAME, source_file=str(PROMPT_FILE))
	file_template = PROMPT_FILE.read_text(encoding="utf-8")
	new_version = mlflow.genai.register_prompt(
		name=PROMPT_NAME,
		template=file_template,
		commit_message="Bootstrap from prompts/job_match_v1.txt",
	)
	mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias=PROMPT_ALIAS, version=new_version.version)
	schema_mode, rubric_version = _load_sidecar_metadata(PROMPT_FILE)
	LOGGER.action(
		"prompt_bootstrap_complete",
		prompt_name=PROMPT_NAME,
		alias=PROMPT_ALIAS,
		version=new_version.version,
		schema_mode=schema_mode,
	)
	_record_history_entry(
		engine,
		PromptActiveHistoryEntry(
			changed_at=datetime.now(timezone.utc).isoformat(),
			from_version=None,
			to_version=str(new_version.version),
			schema_mode=schema_mode,
			rubric_version=rubric_version,
			reason="bootstrap",
		),
	)
	return LoadedPrompt(version=new_version, schema_mode=schema_mode, rubric_version=rubric_version)


def build_loaded_prompt(version_obj: PromptVersion) -> LoadedPrompt:
	"""Wraps an already-fetched PromptVersion (e.g. from a read-only alias lookup a caller does
	itself, like evals/run_offline_eval.py's --prompt-source production with no --prompt-version
	pin) with its resolved schema metadata, without triggering get_active_prompt()'s
	auto-registration side effect.
	"""
	schema_mode, rubric_version = _resolve_schema_mode(version_obj.template)
	return LoadedPrompt(version=version_obj, schema_mode=schema_mode, rubric_version=rubric_version)


def load_prompt_version(version: str) -> LoadedPrompt:
	"""Loads an explicit MLflow-registered prompt version (not necessarily the 'production'
	alias) and resolves its schema metadata the same way get_active_prompt() does. Used by
	POST /admin/active-prompt (to reject aliasing a schema_mode="batch" prompt live) and by
	backfill/eval code that needs to pin a specific version rather than following 'production'.
	"""
	ensure_tracking_uri_configured()
	version_obj = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}/{version}")
	schema_mode, rubric_version = _resolve_schema_mode(version_obj.template)
	return LoadedPrompt(version=version_obj, schema_mode=schema_mode, rubric_version=rubric_version)


def set_active_prompt_version(engine: Engine, version: str, *, reason: str = "manual") -> LoadedPrompt:
	"""Explicitly promotes an already-registered prompt version to the 'production' alias --
	the intended way to cut live scoring over to a new prompt (e.g. v1 -> v4), as opposed to
	get_active_prompt()'s implicit file-diff auto-promotion (kept only as a local-dev
	convenience for iterating on job_match_v1.txt). Refuses to alias a schema_mode="batch"
	prompt live: the ReAct agent's tools (tools/agent_tools.py) only ever score one job per
	call, so a batch-shaped prompt can never be served correctly there.

	This is also the feature flag: whichever version 'production' points to is what every live
	and never-scored-jobs-backfill cycle picks up on its very next run (get_active_prompt() never
	caches). Reverting is just calling this again with an earlier version -- nothing about the
	rows already written under the version being switched away from is touched, purged, or
	invalidated (see revert_active_prompt_version() for the one-click "undo the last switch" path
	built on top of this).
	"""
	loaded = load_prompt_version(version)
	if loaded.schema_mode == "batch":
		raise ValueError(
			f"Prompt version {version!r} has schema_mode='batch' (multi-job per call) and cannot be "
			"set as the live 'production' prompt -- live scoring is always one job per call. Use a "
			"schema_mode='single' or 'legacy' version instead."
		)
	ensure_tracking_uri_configured()
	previous = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@{PROMPT_ALIAS}", allow_missing=True)
	previous_version = str(previous.version) if previous is not None else None

	mlflow.genai.set_prompt_alias(name=PROMPT_NAME, alias=PROMPT_ALIAS, version=loaded.version.version)

	# This is the one log line that marks the exact moment of a prompt cutover -- structured (not
	# plain text) so "when did production last change, and from/to what" is grep-able/queryable
	# the same way every other operational event in this codebase is, rather than only visible by
	# reading MLflow's alias history directly.
	LOGGER.action(
		"prompt_active_version_changed",
		prompt_name=PROMPT_NAME,
		alias=PROMPT_ALIAS,
		from_version=previous_version,
		to_version=loaded.version.version,
		schema_mode=loaded.schema_mode,
		rubric_version=loaded.rubric_version,
		reason=reason,
	)
	_record_history_entry(
		engine,
		PromptActiveHistoryEntry(
			changed_at=datetime.now(timezone.utc).isoformat(),
			from_version=previous_version,
			to_version=str(loaded.version.version),
			schema_mode=loaded.schema_mode,
			rubric_version=loaded.rubric_version,
			reason=reason,
		),
	)
	return loaded


def revert_active_prompt_version(engine: Engine) -> LoadedPrompt:
	"""One-click 'undo the last switch': re-promotes whatever 'production' pointed to immediately
	before the most recent set_active_prompt_version() call, per the recorded history. This is
	the "we can safely revert" half of the feature-flag design -- safe because nothing about
	already-processed rows depends on which version is currently active; job_matches rows are
	permanently tagged with the prompt_version that actually produced them (see
	shared/job_match_data.py's composite PK), so reverting never needs to purge or reconcile any
	data that was written while the version being reverted was active.

	Raises ValueError if there's no recorded switch to undo, or if the most recent recorded
	change was the initial bootstrap (nothing earlier to revert to).
	"""
	history = get_active_prompt_history(engine, limit=1)
	if not history:
		raise ValueError("No prompt version change history to revert -- set_active_prompt_version has never been called.")
	last_change = history[0]
	if last_change.from_version is None:
		raise ValueError(
			f"Cannot revert past the initial bootstrap version {last_change.to_version!r} -- there is no earlier version."
		)
	return set_active_prompt_version(engine, last_change.from_version, reason=f"revert:{last_change.to_version}")


@dataclass(frozen=True)
class RegisteredPromptSummary:
	"""One registered prompt version, for GET /admin/prompts -- the feature-flag selector's
	source of truth for "what can I set active" (as opposed to get_active_prompt_history, which
	is "what has been active and when"), and the Prompt Versions tab's source of truth for "what
	exists at all, live or decommissioned, and what does it actually say".

	`status` ("live" or "decommissioned") comes from prompts/version_status.json, not MLflow --
	MLflow never deletes a registered version, so "decommissioned" here means "no longer eligible
	for new sweep studies", not "removed". `is_active` is a separate concept: whether this is the
	one 'production' alias currently points to. A version can be status="live" without being
	is_active (e.g. job_match_v5.txt's schema_mode="batch" is live but can never be the
	'production' alias -- see set_active_prompt_version()).
	"""

	version: str
	schema_mode: str
	rubric_version: int
	status: str
	template: str
	is_active: bool
	creation_timestamp: int | None


def list_registered_prompt_versions() -> list[RegisteredPromptSummary]:
	ensure_tracking_uri_configured()
	client = MlflowClient()
	try:
		versions = client.search_prompt_versions(PROMPT_NAME)
	except MlflowException as error:
		if error.error_code != "RESOURCE_DOES_NOT_EXIST":
			raise
		return []

	active = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@{PROMPT_ALIAS}", allow_missing=True)
	active_version = str(active.version) if active is not None else None

	summaries = []
	for version_obj in versions:
		schema_mode, rubric_version = _resolve_schema_mode(version_obj.template)
		summaries.append(
			RegisteredPromptSummary(
				version=str(version_obj.version),
				schema_mode=schema_mode,
				rubric_version=rubric_version,
				status=_resolve_prompt_status(version_obj.template),
				template=version_obj.template,
				is_active=(str(version_obj.version) == active_version),
				creation_timestamp=getattr(version_obj, "creation_timestamp", None),
			)
		)
	return sorted(summaries, key=lambda s: int(s.version), reverse=True)


def list_sweep_eligible_versions() -> list[RegisteredPromptSummary]:
	"""Versions POST /evals/sweep is allowed to run against: status="live" (see
	prompts/version_status.json) AND schema_mode="single". schema_mode="batch" is excluded
	regardless of status -- it scores multiple jobs per call and isn't compatible with
	run_offline_eval()'s one-run-per-version sweep loop, the same reason it can never be the
	'production' alias (set_active_prompt_version()). schema_mode="legacy" versions are excluded
	in practice today only because version_status.json marks v1-v3 "decommissioned" -- a future
	live legacy-mode version would still need schema_mode="single" to be swept, since the sweep
	loop always pins prompt_source="production" with a specific version the same way a manual
	single-version trigger does.

	This is the whole "configurable and flexible" mechanism: marking a version "live" in
	version_status.json is necessary but not sufficient for sweep eligibility; it also needs
	schema_mode="single". Today that's v4 only -- v5 is live but schema_mode="batch".
	"""
	return [
		summary
		for summary in list_registered_prompt_versions()
		if summary.status == "live" and summary.schema_mode == "single"
	]


def register_prompt_variants() -> None:
	"""Registers every prompts/job_match_v*.txt file other than PROMPT_FILE (job_match_v1.txt,
	handled by get_active_prompt() above) as an additional version of PROMPT_NAME, skipping any
	whose exact template content is already registered.

	Called once at server startup (see api/app.py's lifespan) so a fresh Railway deploy has every
	variant file in prompts/ available in the MLflow prompt registry immediately -- without this,
	evals/run_offline_eval.py's --prompt-version and POST /admin/active-prompt would have nothing
	to pin/alias against until someone registered them by hand. Idempotent (safe on every
	restart) and never touches the 'production' alias -- only get_active_prompt() (implicitly) or
	set_active_prompt_version() (explicitly) move that.
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
		schema_mode, rubric_version = _load_sidecar_metadata(path)
		LOGGER.action(
			"prompt_variant_registered",
			source_file=path.name,
			prompt_name=PROMPT_NAME,
			version=new_version.version,
			schema_mode=schema_mode,
			rubric_version=rubric_version,
		)
