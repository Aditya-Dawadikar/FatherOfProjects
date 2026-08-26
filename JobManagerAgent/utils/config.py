from __future__ import annotations

from pathlib import Path

from .env_utils import load_env_value


# Anchored off this file's own location (utils/config.py -> JobManagerAgent/) rather than each
# consumer guessing its own relative path -- the previous per-module Path(__file__).with_name(...)
# constants broke silently when their modules moved into subdirectories during the package reorg
# (utils/resume.md, integrations/mlflow/prompts/job_match_v1.txt -- neither exists; the reorg
# never updated the relative path after moving the file that computed it).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESUME_FILE = PROJECT_ROOT / "resume.md"
PROMPT_FILE = PROJECT_ROOT / "prompts" / "job_match_v1.txt"


def load_resume() -> str:
	if not RESUME_FILE.exists():
		raise FileNotFoundError(f"{RESUME_FILE} not found; fill in your resume/skills before running the agent")
	return RESUME_FILE.read_text(encoding="utf-8")


def load_match_threshold() -> int:
	return int(load_env_value("MATCH_THRESHOLD", "70"))


def load_max_jobs_per_cycle() -> int:
	# Kept small on purpose: real throughput is capped at a few requests/minute by the LLM rate
	# limiter (see rate_limiter.py), so a big batch just ties up one cycle for many minutes
	# without checking for new live-trigger events. Smaller batches keep live and backfill work
	# interleaved.
	return int(load_env_value("MAX_JOBS_PER_CYCLE", "5"))


def load_backfill_batch_size() -> int:
	return int(load_env_value("BACKFILL_BATCH_SIZE", str(BACKFILL_BATCH_SIZE)))


def load_provider_rpm_quota() -> int | None:
	value = load_env_value("PROVIDER_RPM_QUOTA", "").strip()
	return int(value) if value else PROVIDER_RPM_QUOTA


# --- Gemini LLM provider (llm_providers/gemini_provider.py) -----------------------------------
DEFAULT_MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.6-flash"
PRIMARY_MODEL_COOLDOWN_KEY = "jobmanageragent:gemini:3.5:cooldown"
PRIMARY_MODEL_COOLDOWN_SECONDS = 600

# gemini-3.x models think by default (usage_metadata.thoughts_token_count), which competes with
# the visible JSON answer for the same output budget -- that silently truncated real responses
# mid-JSON (see incident: MatchResponseError on a response with no closing brace anywhere, not
# just in the logged 200-char preview). thinking_budget=0 was the first fix attempt, but it's the
# pre-Gemini-3 control knob; Gemini 3+ models use thinking_level instead and largely ignore
# thinking_budget, so thinking kept happening anyway (see incident #2: a STOP-finished response
# still truncated mid-string). thinking_level="minimal" is the control that actually reaches
# gemini-3.5/3.6-flash.
#
# A single flat MAX_OUTPUT_TOKENS was still the wrong shape: a single-job call (score_job -- the
# live/ReAct/eval path) only ever needs to fit one job's ~5-criterion JSON, but a batch call
# (score_jobs_batch -- backfill/batch-eval) fits BACKFILL_BATCH_SIZE jobs' worth in the same
# response, on top of the same unpredictable per-call thinking-token overhead -- so a ceiling
# sized for "one job plus thinking" left a batch response no real headroom, and a third incident
# still truncated a 6-job batch partway through job 6 of 6 (the visible JSON for a full batch only
# needs on the order of ~2k tokens; the rest of the old flat 8192 ceiling was thinking tokens even
# at thinking_level="minimal"). Gemini 3 Flash supports up to ~65k output tokens (and a 1M-token
# input window, so the input side was never the constraint here -- resume + a few job postings
# runs a few thousand tokens at most), so there's ample room to size these independently instead
# of sharing one number: SINGLE_JOB_MAX_OUTPUT_TOKENS keeps the original 8192 (score_job never
# had a truncation incident at that size); BATCH_MAX_OUTPUT_TOKENS gets a bigger, separate ceiling
# so a batch's extra thinking+JSON volume doesn't compete with the single-job path's budget.
# score_jobs_batch (llm_providers/__init__.py) logs prompt/completion/total tokens per call so a
# completion count near either ceiling can be correlated with truncation instead of discovered
# after the fact; llm_providers/base.py also recovers whichever leading batch items did complete
# when a response is truncated anyway, rather than discarding the whole batch (_parse_array_partial).
SINGLE_JOB_MAX_OUTPUT_TOKENS = 8192
BATCH_MAX_OUTPUT_TOKENS = 16384
THINKING_LEVEL = "minimal"

# --- Rate limiting (utils/rate_limiter.py) -----------------------------------------------------
#
# The rate-limit budget model: x + y + z + w = the real per-model quota shown in the provider's
# own console (checked manually, never hardcoded from guesswork -- see PROVIDER_RPM_QUOTA below).
#   x = DEFAULT_RPM_CAP    (bucket="live")     -- live matching cycles + the ReAct agent
#   y = BACKFILL_RPM_CAP   (bucket="backfill") -- the backfill/ package's rescore-under-a-new-
#                                                 prompt process (see docs/backfill-design.md)
#   z = EVAL_RPM_CAP       (bucket="eval")     -- evals/run_offline_eval.py
#   w = headroom, unallocated on purpose        -- absorbs anything sharing the same API
#                                                 key/project outside this repo's control
# Each bucket is tracked as an independent Redis sliding-window counter (RedisRpmLimiter.acquire's
# `bucket` param) -- they never share a counter, so none of them can silently eat another's share.
# GET /admin/rate-limits reports live usage against all four for the dashboard's RPM breakdown.
DEFAULT_RPM_CAP = 4
WINDOW_SECONDS = 60.0

# Reserved RPM budget for backfill's own Redis bucket -- deliberately small (a large historical
# backlog can afford to trickle through slowly) so a backfill run can never eat into live
# scoring's share of the real external per-model quota. Override per-model via
# LLM_RPM_CAP__<MODEL>__BACKFILL. Only one backfill run is ever allowed to be "running" at a time
# (see backfill/engine.py's supersession logic) -- this is what keeps "y" a single, cleanly
# reassignable allocation rather than something N concurrent runs would have to split further.
BACKFILL_RPM_CAP = 1

# Reserved RPM budget for the offline eval harness's own bucket -- separate from "live" so a
# triggered eval run (POST /evals, potentially scoring 60+ cases) can't compete with real live
# traffic for the same counter. Override per-model via LLM_RPM_CAP__<MODEL>__EVAL.
EVAL_RPM_CAP = 1

# The real external RPM quota for this model/project, as shown in the provider's own console
# (for Gemini: https://aistudio.google.com/rate-limit) -- set this explicitly per the existing
# "checked in the console, not guessed" policy (see docs/evals-mlflow-design.md's operational
# guidance). Purely informational: nothing in this codebase enforces against it, it only lets
# GET /admin/rate-limits compute and display headroom (w = quota - x - y - z) on the dashboard.
# Left unset (None) by default -- headroom is reported as unknown rather than a guessed number
# until an operator sets PROVIDER_RPM_QUOTA from what they actually see in the console.
PROVIDER_RPM_QUOTA: int | None = None

# How many jobs go into one LLM call when backfilling with a schema_mode="batch" prompt
# (job_match_v5.txt). Bounded by BATCH_MAX_OUTPUT_TOKENS above -- each job's per-criterion
# breakdown (5 criteria, score + 1-2 sentence reasoning each) runs a few hundred output tokens on
# its own, but a batch's response also has to absorb the same unpredictable per-call thinking-token
# overhead a single-job call does, so more jobs per call doesn't just add "a few hundred tokens" of
# safety margin -- capped at 5 to keep a real, comfortable margin under BATCH_MAX_OUTPUT_TOKENS
# rather than pushing batch size up for throughput and eating back into that margin. Override via
# BACKFILL_BATCH_SIZE if a specific model/rubric needs a different budget.
BACKFILL_BATCH_SIZE = 5

# --- Crawler (services/crawler.py) -------------------------------------------------------------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 30

# --- Database tables (shared/job_data.py, shared/job_match_data.py) -------------------------
DEFAULT_JOB_TABLE_NAME = "job_listings"
DEFAULT_JOB_MATCH_TABLE_NAME = "job_matches"

# job_listings.source value for every job scraped from Work at a Startup -- the only source that
# has ever existed, so this is what scripts/migrations/0003_...py backfills pre-existing rows to.
# Ashby/Greenhouse/Lever writers will pass their own source string instead of this constant.
DEFAULT_JOB_SOURCE = "ycombinator"

# --- Migration history tables (backfill/models.py, integrations/mlflow/models.py) -------------
# Durable (Postgres, not Redis) audit trails for the two "what happened during a prompt cutover"
# histories -- see docs/backfill-design.md. Deliberately in Postgres rather than Redis: this is
# audit/history data (survive-anything, queryable, backed up alongside job_matches), not the
# fast/ephemeral operational state Redis is used for elsewhere (RPM counters, the
# unscored-backfill pause flag).
DEFAULT_BACKFILL_RUNS_TABLE_NAME = "backfill_runs"
DEFAULT_PROMPT_ACTIVE_HISTORY_TABLE_NAME = "prompt_active_history"

# --- MLflow prompt registry (integrations/mlflow/prompt_registry.py) ------------------------
PROMPT_NAME = "job_match_prompt"
PROMPT_ALIAS = "production"

# --- Redis streams (integrations/streaming/) ---------------------------------------------------
DEFAULT_SOURCE_STREAM_NAME = "webscraper:events"
DEFAULT_STREAM_NAME = "jobmanageragent:events"
DEFAULT_CONSUMER_GROUP = "jobmanageragent-group"
DEFAULT_CONSUMER_NAME = "jobmanageragent-1"
TRIGGER_EVENT_TYPES = {"pipeline_completed"}
BLOCK_MS = 10_000

# --- System metrics / Prometheus (integrations/metrics/) -------------------------------------
# How often the background collector refreshes the cached CPU/memory/disk/network gauges.
# GET /metrics always serves whatever this collector last wrote -- it never scrapes the OS
# itself -- so this interval is the only knob controlling how fresh (and how expensive) that
# data is.
DEFAULT_METRICS_COLLECTION_INTERVAL_SECONDS = 15.0
# Filesystem path disk usage is sampled from. Left path-shaped (not a fixed "/") because psutil's
# disk_usage() rejects "/" outright on Windows dev machines -- Path.cwd().anchor resolves to the
# right thing on both platforms (e.g. "C:\\" locally, "/" on the Linux Railway deployment).
DEFAULT_METRICS_DISK_PATH = None  # resolved lazily via Path.cwd().anchor, see system_metrics.py

# --- Guardrails (guardrails/) ------------------------------------------------------------------
DEFAULT_GUARDRAIL_TRIGGER_TABLE_NAME = "guardrail_triggers"

# Sanity bound on evaluate_match's reasoning field -- real responses run a short paragraph (the
# golden dataset's longest is well under 500 chars); anything past this is more likely a
# truncated/garbled response or a job posting that hijacked the model's output than real reasoning.
GUARDRAIL_MAX_REASONING_CHARS = 2000

# How many real tool calls (crawl_job, evaluate_match, record_job_result) a well-behaved agent
# makes per job, and how much slack beyond max_jobs_per_cycle * this to allow before
# ToolCallLimitMiddleware (agents/react_agent.py) cuts a run off as a runaway-loop guardrail --
# separate from RECURSION_LIMIT_HEADROOM/STEPS_PER_JOB below, which bound graph *steps*
# (agent-turn + tool-turn), not raw tool-call count.
GUARDRAIL_TOOL_CALLS_PER_JOB = 3
GUARDRAIL_TOOL_CALL_HEADROOM = 4

# Phrases that show up when a scraped job posting is trying to steer the model's output rather
# than describe a job. Deliberately narrow (specific instruction-override phrasing, not generic
# words like "ignore" or "you are now" alone) -- favors missing a novel injection attempt over
# flagging an ordinary job posting's marketing copy as an attack.
GUARDRAIL_INJECTION_PATTERNS = (
	r"ignore (all |any |your )?(previous|prior|above|earlier) instructions",
	r"disregard (all |any |your )?(previous|prior|above|earlier) instructions",
	r"override (your |the )?(system |previous )?instructions",
	r"you are now (an ai|a helpful|acting as|in developer mode)",
	r"\bsystem prompt\b",
	r"new instructions?:\s",
	r"\bassistant:\s",
	r"\bsystem:\s",
	r"give (this|the) candidate (a |an )?(perfect|100|maximum) (score|match)",
	r"always (respond|reply|answer) with match_score",
)

# --- ReAct agent loop (agents/react_agent.py) -----------------------------------------------
# Bounds the ReAct loop. Empirically, this LangGraph version costs ~2 recursion-limit "steps"
# per AI-message turn (agent node + tool node), whether or not that turn makes a tool call --
# confirmed by a scripted 3-job test (1 fetch turn + 3 tool-call turns/job + 1 final stop turn =
# 11 turns) failing at limit=17 and succeeding at limit=18. Per job that's 3 tool calls
# (crawl_job, evaluate_match, record_job_result) * 2 steps = 6, plus headroom covering the
# initial fetch turn, the final stop turn, and slack for the model taking a couple of extra
# reasoning-only turns. Without a cap, a model stuck reasoning in circles could burn the RPM
# budget indefinitely on a single cycle.
RECURSION_LIMIT_HEADROOM = 14
STEPS_PER_JOB = 6
