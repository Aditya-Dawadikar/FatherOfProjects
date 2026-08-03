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
# gemini-3.5/3.6-flash. MAX_OUTPUT_TOKENS is set generously on top of that as headroom, since
# Gemini 3 thinking models aren't guaranteed to allow thinking all the way down to zero.
MAX_OUTPUT_TOKENS = 8192
THINKING_LEVEL = "minimal"

# --- Rate limiting (utils/rate_limiter.py) -----------------------------------------------------
DEFAULT_RPM_CAP = 4
WINDOW_SECONDS = 60.0

# --- Crawler (services/crawler.py) -------------------------------------------------------------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 30

# --- Database tables (shared/job_data.py, shared/job_match_data.py) -------------------------
DEFAULT_JOB_TABLE_NAME = "job_listings"
DEFAULT_JOB_MATCH_TABLE_NAME = "job_matches"

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
