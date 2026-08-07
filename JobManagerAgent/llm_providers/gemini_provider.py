from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from redis import Redis
from redis.exceptions import RedisError

from utils.config import (
	DEFAULT_MODEL,
	FALLBACK_MODEL,
	MAX_OUTPUT_TOKENS,
	PRIMARY_MODEL_COOLDOWN_KEY,
	PRIMARY_MODEL_COOLDOWN_SECONDS,
	THINKING_LEVEL,
)
from utils.env_utils import load_env_value
from utils.rate_limiter import RedisRpmLimiter, load_backfill_rpm_cap

from .base import MatchResponseError, RateLimitError, TokenUsage, TransientProviderError


_RPM_LIMITER: RedisRpmLimiter | None = None


def _rpm_limiter() -> RedisRpmLimiter:
	# Lazy singleton: constructing RedisRpmLimiter requires REDIS_URL, and failing loudly the
	# first time a call is actually attempted (rather than at import time, or silently, like
	# the cooldown client below) is the right failure mode for something that exists to
	# protect a quota shared with another application.
	global _RPM_LIMITER
	if _RPM_LIMITER is None:
		_RPM_LIMITER = RedisRpmLimiter()
	return _RPM_LIMITER


_COOLDOWN_REDIS_CLIENT: Redis | None = None
_COOLDOWN_REDIS_INIT_DONE = False


def load_model() -> str:
	return load_env_value("GEMINI_MODEL", DEFAULT_MODEL)


def build_client() -> genai.Client:
	return genai.Client(api_key=load_env_value("GEMINI_API_KEY"))


def _load_cooldown_seconds() -> int:
	value = load_env_value("GEMINI_PRIMARY_MODEL_COOLDOWN_SECONDS", str(PRIMARY_MODEL_COOLDOWN_SECONDS))
	try:
		seconds = int(value)
	except ValueError:
		seconds = PRIMARY_MODEL_COOLDOWN_SECONDS
	return max(1, seconds)


def _load_cooldown_key() -> str:
	return load_env_value("GEMINI_PRIMARY_MODEL_COOLDOWN_KEY", PRIMARY_MODEL_COOLDOWN_KEY)


def _cooldown_redis_client() -> Redis | None:
	global _COOLDOWN_REDIS_CLIENT, _COOLDOWN_REDIS_INIT_DONE
	if _COOLDOWN_REDIS_INIT_DONE:
		return _COOLDOWN_REDIS_CLIENT

	_COOLDOWN_REDIS_INIT_DONE = True
	try:
		redis_url = load_env_value("REDIS_URL")
	except KeyError:
		return None

	_COOLDOWN_REDIS_CLIENT = Redis.from_url(redis_url, decode_responses=True)
	return _COOLDOWN_REDIS_CLIENT


def _is_primary_in_cooldown() -> bool:
	client = _cooldown_redis_client()
	if client is None:
		return False

	try:
		return bool(client.get(_load_cooldown_key()))
	except RedisError:
		return False


def _set_primary_cooldown(error: Exception) -> None:
	client = _cooldown_redis_client()
	if client is None:
		return

	try:
		client.set(_load_cooldown_key(), type(error).__name__, ex=_load_cooldown_seconds())
	except RedisError:
		return


def _usage_from_response(response: genai_types.GenerateContentResponse) -> TokenUsage:
	usage = response.usage_metadata
	prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
	output_tokens = getattr(usage, "candidates_token_count", None) or 0
	thoughts_tokens = getattr(usage, "thoughts_token_count", None) or 0
	# total_token_count is the provider's own authoritative sum (billing runs off this, not our
	# reconstruction of it) -- only fall back to adding the parts ourselves if it's missing.
	total_tokens = getattr(usage, "total_token_count", None) or (prompt_tokens + output_tokens + thoughts_tokens)
	return TokenUsage(
		prompt_tokens=prompt_tokens,
		completion_tokens=output_tokens + thoughts_tokens,
		total_tokens=total_tokens,
	)


def _generate_content(client: genai.Client, *, model: str, prompt: str, bucket: str = "live") -> tuple[str, TokenUsage]:
	# Single choke point for every actual network call this provider makes (primary and
	# fallback both route through here), so the RPM budget is enforced no matter which branch
	# of call_model/_call_fallback_model reached it. `bucket` ("live" or "backfill", threaded
	# down from score_job/score_jobs_batch via call_scoring_model) determines which independent
	# sliding-window counter this call draws from and which cap applies -- this is the actual
	# enforcement point for the reserved backfill RPM budget (see RedisRpmLimiter.acquire and
	# utils/config.py:BACKFILL_RPM_CAP); a caller-side acquire() on its own is not enough, since
	# every real call has to pass through here regardless of who called it.
	cap = load_backfill_rpm_cap(model) if bucket == "backfill" else None
	_rpm_limiter().acquire(model, cap=cap, bucket=bucket)
	response = client.models.generate_content(
		model=model,
		contents=prompt,
		config=genai_types.GenerateContentConfig(
			temperature=0,
			response_mime_type="application/json",
			max_output_tokens=MAX_OUTPUT_TOKENS,
			thinking_config=genai_types.ThinkingConfig(thinking_level=THINKING_LEVEL),
		),
	)
	_raise_if_truncated(response, model=model)
	return response.text or "", _usage_from_response(response)


def _raise_if_truncated(response: genai_types.GenerateContentResponse, *, model: str) -> None:
	candidates = response.candidates or []
	if not candidates:
		return

	finish_reason = candidates[0].finish_reason
	if finish_reason in (None, genai_types.FinishReason.STOP):
		return

	usage = response.usage_metadata
	raise MatchResponseError(
		f"Gemini response for model={model} did not finish normally "
		f"(finish_reason={finish_reason}); thoughts_tokens="
		f"{getattr(usage, 'thoughts_token_count', None)} output_tokens="
		f"{getattr(usage, 'candidates_token_count', None)} max_output_tokens={MAX_OUTPUT_TOKENS}"
	)


def _should_try_fallback(*, model: str) -> bool:
	return model == DEFAULT_MODEL and FALLBACK_MODEL != DEFAULT_MODEL


def _call_fallback_model(client: genai.Client, *, prompt: str, bucket: str = "live") -> tuple[str, TokenUsage]:
	try:
		return _generate_content(client, model=FALLBACK_MODEL, prompt=prompt, bucket=bucket)
	except genai_errors.ClientError as fallback_error:
		if fallback_error.code == 429:
			raise RateLimitError(str(fallback_error)) from fallback_error
		raise
	except genai_errors.ServerError as fallback_error:
		raise TransientProviderError(str(fallback_error)) from fallback_error


def call_model(client: genai.Client, *, model: str, prompt: str, bucket: str = "live") -> tuple[str, TokenUsage]:
	if _should_try_fallback(model=model) and _is_primary_in_cooldown():
		return _call_fallback_model(client, prompt=prompt, bucket=bucket)

	try:
		return _generate_content(client, model=model, prompt=prompt, bucket=bucket)
	except genai_errors.ClientError as error:
		if _should_try_fallback(model=model):
			_set_primary_cooldown(error)
			return _call_fallback_model(client, prompt=prompt, bucket=bucket)

		if error.code == 429:
			raise RateLimitError(str(error)) from error

		raise
	except genai_errors.ServerError as error:
		if _should_try_fallback(model=model):
			_set_primary_cooldown(error)
			return _call_fallback_model(client, prompt=prompt, bucket=bucket)

		# 5xx from Gemini -- most commonly 503 "currently experiencing high demand", which its
		# own error message says is usually temporary, so worth a retry rather than failing hard.
		raise TransientProviderError(str(error)) from error
