from __future__ import annotations

from fastapi import APIRouter, HTTPException
from mlflow.exceptions import MlflowException
from pydantic import BaseModel, Field

from integrations.mlflow import (
	PROMPT_ALIAS,
	PROMPT_NAME,
	get_active_prompt_history,
	list_registered_prompt_versions,
	revert_active_prompt_version,
	set_active_prompt_version,
)
from shared.job_data import get_shared_engine
from utils.agent_logger import get_agent_logger
from utils.config import DEFAULT_MODEL, WINDOW_SECONDS, load_provider_rpm_quota
from utils.matching_controls import (
	pause_unscored_backfill,
	resume_unscored_backfill,
	unscored_backfill_pause_reason,
)
from utils.rate_limiter import RPM_BUCKETS, RedisRpmLimiter


LOGGER = get_agent_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class SetActivePromptRequest(BaseModel):
	version: str


class SetActivePromptResponse(BaseModel):
	prompt_name: str
	alias: str
	version: str
	schema_mode: str
	rubric_version: int


@router.post("/active-prompt", summary="Promote a registered prompt version to production")
def set_active_prompt(payload: SetActivePromptRequest) -> SetActivePromptResponse:
	"""Explicitly cuts future live scoring over to `version` (an already-registered prompt
	version number, e.g. "4") -- the only way to change what's active once anything has been
	aliased (get_active_prompt() only auto-registers/aliases on first-ever bootstrap; see its
	docstring for why it used to silently revert this on the next cycle, and no longer does).
	Rejects a schema_mode="batch" version (e.g. job_match_v5.txt) -- live scoring is always one
	job per call, via the ReAct agent's tools.

	Takes effect on the very next live/backfill cycle -- get_active_prompt() re-resolves the
	'production' alias fresh every cycle rather than caching it, and every cycle logs a
	`cycle_prompt_resolved` action with the version it used (see agents/react_agent.py), which is
	the log line to check to confirm a cutover actually took effect.

	Decommissioning an old version needs no separate action: it stays registered in MLflow
	(nothing is ever deleted), it just stops being what 'production' points to.

	For a predictable cutover window with no never-scored-jobs backfill cycles in flight, pair
	this with POST /admin/unscored-backfill/pause beforehand and
	POST /admin/unscored-backfill/resume afterward.
	"""
	try:
		loaded = set_active_prompt_version(get_shared_engine(), payload.version)
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error
	except MlflowException as error:
		raise HTTPException(status_code=404, detail=f"Prompt version {payload.version!r} not found: {error}") from error

	return SetActivePromptResponse(
		prompt_name=PROMPT_NAME,
		alias=PROMPT_ALIAS,
		version=loaded.version_id,
		schema_mode=loaded.schema_mode,
		rubric_version=loaded.rubric_version,
	)


@router.post("/active-prompt/revert", summary="Revert to the previously active prompt version")
def revert_active_prompt() -> SetActivePromptResponse:
	"""One-click undo of the most recent POST /admin/active-prompt call -- re-promotes whatever
	'production' pointed to immediately before it, per the recorded history
	(GET /admin/active-prompt/history). Safe by construction: job_matches rows are permanently
	tagged with the prompt_version that actually scored them, so nothing about data written while
	the version being reverted was active needs to be purged, rolled back, or reconciled --
	reverting is just pointing 'production' at an earlier already-registered version, the exact
	same operation POST /admin/active-prompt performs, with the earlier version looked up
	automatically instead of specified by hand.

	400s if there's no recorded switch to undo (nothing has ever called
	POST /admin/active-prompt), or if the most recent recorded change was the initial bootstrap.
	"""
	try:
		loaded = revert_active_prompt_version(get_shared_engine())
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error

	return SetActivePromptResponse(
		prompt_name=PROMPT_NAME,
		alias=PROMPT_ALIAS,
		version=loaded.version_id,
		schema_mode=loaded.schema_mode,
		rubric_version=loaded.rubric_version,
	)


class PromptActiveHistoryEntryResponse(BaseModel):
	changed_at: str
	from_version: str | None
	to_version: str
	schema_mode: str
	rubric_version: int
	reason: str


@router.get(
	"/active-prompt/history",
	summary="Recent 'production' alias changes (the migration handoff timeline)",
)
def get_active_prompt_history_endpoint(limit: int = 50) -> list[PromptActiveHistoryEntryResponse]:
	"""Durable, most-recent-first record of every prompt cutover (bootstrap, manual
	POST /admin/active-prompt calls, and reverts) -- survives redeploys (Postgres-backed, not
	in-process memory or Redis), which is exactly when an operator following the migration
	sequence in docs/backfill-design.md needs to check "what actually happened, and when."
	"""
	return [
		PromptActiveHistoryEntryResponse(
			changed_at=entry.changed_at,
			from_version=entry.from_version,
			to_version=entry.to_version,
			schema_mode=entry.schema_mode,
			rubric_version=entry.rubric_version,
			reason=entry.reason,
		)
		for entry in get_active_prompt_history(get_shared_engine(), limit=limit)
	]


class RegisteredPromptResponse(BaseModel):
	version: str
	schema_mode: str
	rubric_version: int
	is_active: bool


@router.get("/prompts", summary="List every registered prompt version -- the feature-flag selector's source list")
def list_prompts() -> list[RegisteredPromptResponse]:
	"""Every prompt version ever registered (nothing is ever deleted -- see
	docs/backfill-design.md), newest first, with `is_active` marking whichever one 'production'
	currently points to. This is what the dashboard's feature-flag dropdown is built from --
	batch-mode versions (schema_mode="batch", e.g. job_match_v5.txt) are included for visibility
	but POST /admin/active-prompt rejects setting one active.
	"""
	return [
		RegisteredPromptResponse(
			version=summary.version,
			schema_mode=summary.schema_mode,
			rubric_version=summary.rubric_version,
			is_active=summary.is_active,
		)
		for summary in list_registered_prompt_versions()
	]


class UnscoredBackfillPauseRequest(BaseModel):
	reason: str = Field(
		default="manual_pause",
		description="Why it's being paused -- echoed back in status and in the "
		"unscored_backfill_paused log/status, useful when coordinating a prompt cutover.",
	)


class UnscoredBackfillStatusResponse(BaseModel):
	paused: bool
	reason: str | None


@router.post(
	"/unscored-backfill/pause",
	summary="Pause the never-scored-jobs backfill (idle-triggered) cycles",
)
def pause_unscored_backfill_endpoint(payload: UnscoredBackfillPauseRequest) -> UnscoredBackfillStatusResponse:
	"""Pauses ONLY mode="backfill" cycles -- stream_consumer.py's idle-triggered draining of jobs
	that have never been scored under any prompt version (see agents/react_agent.py,
	api/agent_worker.py:on_idle). Live cycles (mode="live", triggered by pipeline_completed
	events or boot catch-up) are never affected by this and keep running.

	This is NOT the backfill/ package's rescore-under-a-new-prompt process (POST /backfill/run)
	-- that's a separate, already-decoupled mechanism (its own reserved RPM bucket, its own
	candidate query) that doesn't need pausing around a cutover. This endpoint exists purely to
	give an operator a clean, predictable window during a prompt cutover: pause here, call
	POST /admin/active-prompt, then POST /admin/unscored-backfill/resume. It is not required for
	correctness -- get_active_prompt() re-resolves 'production' fresh on every cycle regardless,
	so an unpaused backfill cycle mid-cutover would, at worst, score one small batch
	(MAX_JOBS_PER_CYCLE jobs) under the outgoing prompt version, which then just becomes ordinary
	backlog for a later POST /backfill/run to pick up.
	"""
	pause_unscored_backfill(reason=payload.reason)
	LOGGER.action("unscored_backfill_paused", reason=payload.reason)
	return UnscoredBackfillStatusResponse(paused=True, reason=payload.reason)


@router.post(
	"/unscored-backfill/resume",
	summary="Resume the never-scored-jobs backfill (idle-triggered) cycles",
)
def resume_unscored_backfill_endpoint() -> UnscoredBackfillStatusResponse:
	resume_unscored_backfill()
	LOGGER.action("unscored_backfill_resumed")
	return UnscoredBackfillStatusResponse(paused=False, reason=None)


@router.get(
	"/unscored-backfill/status",
	summary="Check whether the never-scored-jobs backfill is currently paused",
)
def unscored_backfill_status_endpoint() -> UnscoredBackfillStatusResponse:
	reason = unscored_backfill_pause_reason()
	return UnscoredBackfillStatusResponse(paused=reason is not None, reason=reason)


class RpmBucketUsage(BaseModel):
	bucket: str
	model: str
	count: int
	cap: int
	remaining: int


class RpmBreakdownResponse(BaseModel):
	model: str
	window_seconds: float
	buckets: list[RpmBucketUsage]
	total_allocated: int
	provider_quota: int | None
	headroom: int | None


@router.get(
	"/rate-limits",
	summary="Real-time RPM usage per bucket (live/backfill/eval) + headroom",
)
def get_rate_limits() -> RpmBreakdownResponse:
	"""The x+y+z+w budget model (see utils/config.py) made visible: current in-window request
	count and cap for each independently-tracked bucket -- "live" (x, live matching cycles),
	"backfill" (y, the rescore-under-a-new-prompt process), "eval" (z, the offline eval harness)
	-- plus `headroom` (w), computed as PROVIDER_RPM_QUOTA minus the sum of the three caps when an
	operator has set PROVIDER_RPM_QUOTA from the provider's own console; null/unset otherwise
	rather than guessed. This is a read-only peek (RedisRpmLimiter.current_usage) -- polling it
	never itself consumes budget.
	"""
	limiter = RedisRpmLimiter()
	usages = [limiter.current_usage(DEFAULT_MODEL, bucket) for bucket in RPM_BUCKETS]
	total_allocated = sum(usage.cap for usage in usages)
	quota = load_provider_rpm_quota()
	headroom = (quota - total_allocated) if quota is not None else None

	return RpmBreakdownResponse(
		model=DEFAULT_MODEL,
		window_seconds=WINDOW_SECONDS,
		buckets=[
			RpmBucketUsage(bucket=usage.bucket, model=usage.model, count=usage.count, cap=usage.cap, remaining=usage.remaining)
			for usage in usages
		],
		total_allocated=total_allocated,
		provider_quota=quota,
		headroom=headroom,
	)
