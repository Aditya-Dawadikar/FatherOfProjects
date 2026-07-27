from __future__ import annotations

from typing import Any

import groq

from env_utils import load_env_value

from .base import RateLimitError, TransientProviderError


DEFAULT_MODEL = "llama-3.3-70b-versatile"


def load_model() -> str:
	return load_env_value("GROQ_MODEL", DEFAULT_MODEL)


def build_client() -> groq.Groq:
	return groq.Groq(api_key=load_env_value("GROQ_API_KEY"))


def _retry_after_seconds(error: groq.RateLimitError) -> float | None:
	header_value = error.response.headers.get("retry-after") if error.response is not None else None
	if header_value is None:
		return None
	try:
		return float(header_value)
	except ValueError:
		return None


def call_model(client: Any, *, model: str, prompt: str) -> str:
	try:
		response = client.chat.completions.create(
			model=model,
			messages=[{"role": "user", "content": prompt}],
			temperature=0,
			response_format={"type": "json_object"},
		)
	except groq.RateLimitError as error:
		raise RateLimitError(str(error), retry_after=_retry_after_seconds(error)) from error
	except (groq.InternalServerError, groq.APIConnectionError) as error:
		# InternalServerError = 5xx from Groq itself; APIConnectionError (and its subclass
		# APITimeoutError) = the request never got a response at all -- both are worth a retry.
		raise TransientProviderError(str(error)) from error
	return response.choices[0].message.content or ""
