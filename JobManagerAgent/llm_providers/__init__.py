from __future__ import annotations

from types import ModuleType
from typing import Any

from env_utils import load_env_value

from . import gemini_provider, groq_provider
from .base import MatchResponseError, RateLimitError, parse_match_response, render_prompt


__all__ = [
	"MatchResponseError",
	"RateLimitError",
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
	text = _provider_module(provider).call_model(client, model=model, prompt=prompt)
	return parse_match_response(text)
