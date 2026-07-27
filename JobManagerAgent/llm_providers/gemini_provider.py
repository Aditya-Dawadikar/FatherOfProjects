from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from env_utils import load_env_value

from .base import RateLimitError, TransientProviderError


DEFAULT_MODEL = "gemini-3.5-flash"


def load_model() -> str:
	return load_env_value("GEMINI_MODEL", DEFAULT_MODEL)


def build_client() -> genai.Client:
	return genai.Client(api_key=load_env_value("GEMINI_API_KEY"))


def call_model(client: genai.Client, *, model: str, prompt: str) -> str:
	try:
		response = client.models.generate_content(
			model=model,
			contents=prompt,
			config=genai_types.GenerateContentConfig(
				temperature=0,
				response_mime_type="application/json",
			),
		)
	except genai_errors.ClientError as error:
		if error.code == 429:
			raise RateLimitError(str(error)) from error
		raise
	except genai_errors.ServerError as error:
		# 5xx from Gemini -- most commonly 503 "currently experiencing high demand", which its
		# own error message says is usually temporary, so worth a retry rather than failing hard.
		raise TransientProviderError(str(error)) from error
	return response.text or ""
