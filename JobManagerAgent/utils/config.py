from __future__ import annotations

from pathlib import Path

from .env_utils import load_env_value


RESUME_FILE = Path(__file__).with_name("resume.md")


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
