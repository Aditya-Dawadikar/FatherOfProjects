"""Cumulative Gemini token spend, tracked against an operator-configured TOKEN_BUDGET, plus a
persistent flag for "the provider told us we're out of prepaid credits" (a 429 RESOURCE_EXHAUSTED
carrying a billing-specific message, as opposed to an ordinary per-minute rate limit that clears
on its own -- see gemini_provider.py:_is_billing_exhausted_message).

Backed by Redis, not Postgres, mirroring RedisRpmLimiter and the primary-model cooldown flag
(rate_limiter.py, gemini_provider.py) -- this is operational state about "how is our current API
key doing", the same category of thing those already track, not an audit trail like
backfill_runs/prompt_active_history. The tradeoff: a full Redis flush (not just an app redeploy --
a managed Redis instance survives those) resets the counter; POST /admin/token-budget/reset exists
for the legitimate case anyway (an operator topping up credits and starting a fresh tracking
period), so losing the running total on a rare Redis flush isn't a real gap.

Deliberately only counts tokens that flow through gemini_provider.py's _generate_content (the
"single choke point for every actual network call this provider makes" for score_job/
score_jobs_batch) -- agents/react_agent.py's orchestration LLM (decides which tool to call next,
via langchain_google_genai.ChatGoogleGenerativeAI directly, not through this module) is not
included. That call is much smaller and far less frequent than the actual scoring calls it
orchestrates, so this still tracks the overwhelming majority of real spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from redis import Redis

from .env_utils import load_env_value


_KEY_PREFIX = "jobmanageragent:token_budget"
_TOKENS_USED_KEY = f"{_KEY_PREFIX}:tokens_used"
_PERIOD_STARTED_KEY = f"{_KEY_PREFIX}:period_started_at"
_EXHAUSTED_AT_KEY = f"{_KEY_PREFIX}:billing_exhausted_at"
_EXHAUSTED_MESSAGE_KEY = f"{_KEY_PREFIX}:billing_exhausted_message"

_CLIENT: Redis | None = None


def _client() -> Redis:
	global _CLIENT
	if _CLIENT is None:
		_CLIENT = Redis.from_url(load_env_value("REDIS_URL"), decode_responses=True)
	return _CLIENT


def load_token_budget() -> int | None:
	"""The operator-configured total token allowance for the current tracking period -- e.g.
	sized off however many tokens the current prepaid credit balance covers at the model's
	per-token price. Checked explicitly via the TOKEN_BUDGET env var, never guessed, same policy
	as PROVIDER_RPM_QUOTA (utils/config.py). None means "no budget configured" -- remaining is
	reported as unknown rather than computed against a made-up ceiling.
	"""
	value = load_env_value("TOKEN_BUDGET", "").strip()
	return int(value) if value else None


def record_tokens(total_tokens: int) -> None:
	"""Called once per successful real network call (gemini_provider.py:_generate_content) with
	that call's total_tokens (prompt + completion, thinking included -- see TokenUsage). Sets
	period_started_at on the very first call of a period (NX -- never overwritten by a later
	call) so GET /admin/token-budget can report how long the current period has been running.
	"""
	client = _client()
	client.set(_PERIOD_STARTED_KEY, datetime.now(timezone.utc).isoformat(), nx=True)
	client.incrby(_TOKENS_USED_KEY, total_tokens)


def record_billing_exhausted(message: str) -> None:
	"""Called the moment a 429 is identified as billing exhaustion (not an ordinary rate limit)
	-- persisted immediately, independent of whatever the caller that triggered it goes on to do
	with the raised BillingExhaustedError, so the dashboard alert doesn't depend on every call
	site remembering to report it.
	"""
	client = _client()
	now = datetime.now(timezone.utc).isoformat()
	client.set(_EXHAUSTED_AT_KEY, now)
	client.set(_EXHAUSTED_MESSAGE_KEY, message)


@dataclass(frozen=True)
class TokenBudgetStatus:
	tokens_used: int
	budget: int | None
	remaining: int | None
	period_started_at: str | None
	is_billing_exhausted: bool
	billing_exhausted_at: str | None
	billing_exhausted_message: str | None


def get_token_budget_status() -> TokenBudgetStatus:
	client = _client()
	tokens_used = int(client.get(_TOKENS_USED_KEY) or 0)
	budget = load_token_budget()
	exhausted_at = client.get(_EXHAUSTED_AT_KEY)
	return TokenBudgetStatus(
		tokens_used=tokens_used,
		budget=budget,
		remaining=(budget - tokens_used) if budget is not None else None,
		period_started_at=client.get(_PERIOD_STARTED_KEY),
		is_billing_exhausted=exhausted_at is not None,
		billing_exhausted_at=exhausted_at,
		billing_exhausted_message=client.get(_EXHAUSTED_MESSAGE_KEY),
	)


def reset_token_budget() -> None:
	"""Starts a new tracking period -- e.g. after topping up prepaid credits. Clears the
	billing-exhausted flag too: a reset is the operator explicitly saying the problem is
	addressed, not just the counter being wiped by accident.
	"""
	_client().delete(_TOKENS_USED_KEY, _PERIOD_STARTED_KEY, _EXHAUSTED_AT_KEY, _EXHAUSTED_MESSAGE_KEY)
