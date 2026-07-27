from __future__ import annotations

import time
from types import ModuleType
from typing import Any

from env_utils import load_env_value

from . import gemini_provider, groq_provider
from .base import MatchResponseError, RateLimitError, TransientProviderError, parse_match_response, render_prompt


__all__ = [
	"MatchResponseError",
	"RateLimitError",
	"TransientProviderError",
	"build_client",
	"evaluate_match",
	"load_model_name",
	"load_provider_name",
	"parse_match_response",
	"render_prompt",
]

_PROVIDERS: dict[str, ModuleType] = {
	"groq": groq_provider,
	"gemini": gemini_provider,
}

_TRANSIENT_MAX_RETRIES = 3
_TRANSIENT_BASE_DELAY_SECONDS = 2.0


def load_provider_name() -> str:
	name = load_env_value("LLM_PROVIDER", "gemini").strip().lower()
	if name not in _PROVIDERS:
		raise ValueError(f"Unknown LLM_PROVIDER {name!r}; expected one of {sorted(_PROVIDERS)}")
	return name


def _provider_module(provider: str | None) -> ModuleType:
	return _PROVIDERS[provider or load_provider_name()]


def load_model_name(provider: str | None = None) -> str:
	return _provider_module(provider).load_model()


def build_client(provider: str | None = None) -> Any:
	return _provider_module(provider).build_client()


def evaluate_match(client: Any, *, model: str, prompt: str, provider: str | None = None) -> dict[str, Any]:
	module = _provider_module(provider)

	attempt = 0
	while True:
		try:
			text = module.call_model(client, model=model, prompt=prompt)
			break
		except TransientProviderError:
			attempt += 1
			if attempt > _TRANSIENT_MAX_RETRIES:
				raise
			# Exponential backoff (2s, 4s, 8s): a 5xx/overloaded/timeout error is, per the
			# provider's own error message in the common case, usually temporary within seconds
			# -- worth a few retries here rather than immediately failing the whole job the way
			# RateLimitError does (a quota, unlike load, won't clear by waiting this briefly).
			time.sleep(_TRANSIENT_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))

	return parse_match_response(text)
