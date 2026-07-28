from __future__ import annotations

import logging
import time
from typing import Any

from utils.env_utils import load_env_value

from . import gemini_provider
from .base import (
	JobScore,
	MatchResponseError,
	RateLimitError,
	TransientProviderError,
	parse_match_response,
	render_prompt,
)


__all__ = [
	"JobScore",
	"MatchResponseError",
	"RateLimitError",
	"TransientProviderError",
	"build_client",
	"evaluate_match",
	"load_model_name",
	"load_provider_name",
	"parse_match_response",
	"render_prompt",
	"score_job",
]

_ONLY_PROVIDER = "gemini"

_TRANSIENT_MAX_RETRIES = 3
_TRANSIENT_BASE_DELAY_SECONDS = 2.0

# A RateLimitError reaching here should be rare if the caller's own RPM budget (rate_limiter.py)
# is working -- it most often means something outside this process (e.g. another application on
# the same API key) consumed quota within the same window. Worth a couple of short retries with
# backoff before giving up, same reasoning as the TransientProviderError retry above but on a
# longer/explicit delay (the provider's own retry_after when it gives one) rather than fast
# exponential backoff, since a quota window reopening takes longer than a transient glitch
# clearing.
_RATE_LIMIT_MAX_RETRIES = 2
_RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 15.0

LOGGER = logging.getLogger(__name__)


def load_provider_name() -> str:
	name = load_env_value("LLM_PROVIDER", _ONLY_PROVIDER).strip().lower()
	if name and name != _ONLY_PROVIDER:
		raise ValueError(f"Unsupported LLM_PROVIDER {name!r}; only {_ONLY_PROVIDER!r} is supported")
	return _ONLY_PROVIDER


def _provider_module(provider: str | None) -> Any:
	resolved = (provider or load_provider_name()).strip().lower()
	if resolved != _ONLY_PROVIDER:
		raise ValueError(f"Unsupported provider {resolved!r}; only {_ONLY_PROVIDER!r} is supported")
	return gemini_provider


def load_model_name(provider: str | None = None) -> str:
	return _provider_module(provider).load_model()


def build_client(provider: str | None = None) -> Any:
	return _provider_module(provider).build_client()


def evaluate_match(client: Any, *, model: str, prompt: str, provider: str | None = None) -> dict[str, Any]:
	"""Single LLM scoring call, with retries for the two recoverable failure modes a provider
	call can hit: a transient server-side hiccup (fast exponential backoff) and a rate limit
	(longer backoff, informed by the provider's retry_after when given). Both retry loops run
	here so every caller -- the live/backfill cycle, the ReAct agent's evaluate_match tool, and
	the offline eval harness -- gets the same resilience without redefining it."""
	module = _provider_module(provider)

	transient_attempt = 0
	rate_limit_attempt = 0
	while True:
		try:
			text = module.call_model(client, model=model, prompt=prompt)
			break
		except TransientProviderError:
			transient_attempt += 1
			if transient_attempt > _TRANSIENT_MAX_RETRIES:
				raise
			delay = _TRANSIENT_BASE_DELAY_SECONDS * (2 ** (transient_attempt - 1))
			LOGGER.info("Transient provider error, retrying in %.1fs (attempt %d)", delay, transient_attempt)
			time.sleep(delay)
		except RateLimitError as error:
			rate_limit_attempt += 1
			if rate_limit_attempt > _RATE_LIMIT_MAX_RETRIES:
				raise
			delay = error.retry_after or _RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
			LOGGER.info("Rate limited, retrying in %.1fs (attempt %d)", delay, rate_limit_attempt)
			time.sleep(delay)

	return parse_match_response(text)


def score_job(
	*,
	client: Any,
	model: str,
	provider: str | None = None,
	prompt_version: Any,
	resume: str,
	job: dict[str, Any],
	threshold: int,
) -> JobScore:
	"""The single definition of 'evaluate one job against the resume': renders the active prompt
	template, scores it via evaluate_match (which already retries transient/rate-limit failures),
	and applies the match threshold. Used identically by the ReAct agent's evaluate_match tool
	(tools/agent_tools.py) and the offline eval harness (evals/run_offline_eval.py) -- there is
	exactly one place "is this a match" gets decided, so the two can never quietly drift apart.
	"""
	prompt = render_prompt(prompt_version, resume=resume, job=job)
	result = evaluate_match(client, model=model, prompt=prompt, provider=provider)
	return JobScore(
		match_score=result["match_score"],
		reasoning=result["reasoning"],
		is_match=result["match_score"] >= threshold,
	)
