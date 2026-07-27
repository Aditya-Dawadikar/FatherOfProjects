from __future__ import annotations

from typing import Any

import requests

from env_utils import load_env_value

from .base import TransientProviderError


DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_BASE_URL = "http://localhost:11434"
REQUEST_TIMEOUT_SECONDS = 120  # CPU inference on an 8B model is much slower than a hosted API.


def load_model() -> str:
	return load_env_value("OLLAMA_MODEL", DEFAULT_MODEL)


def build_client() -> requests.Session:
	return requests.Session()


def call_model(client: requests.Session, *, model: str, prompt: str) -> str:
	base_url = load_env_value("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
	try:
		response = client.post(
			f"{base_url}/api/chat",
			json={
				"model": model,
				"messages": [{"role": "user", "content": prompt}],
				"format": "json",
				"stream": False,
				"options": {"temperature": 0},
			},
			timeout=REQUEST_TIMEOUT_SECONDS,
		)
	except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
		# Self-hosted, so this is almost always "the server is still starting up, still loading
		# the model into memory, or got restarted" -- worth a retry, unlike a genuinely bad request.
		raise TransientProviderError(str(error)) from error

	if response.status_code >= 500:
		raise TransientProviderError(f"Ollama returned {response.status_code}: {response.text[:300]}")
	response.raise_for_status()

	return response.json()["message"]["content"]
