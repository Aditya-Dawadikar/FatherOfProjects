from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).with_name(".env")


def load_env_value(key: str, default: str | None = None) -> str:
	value = os.getenv(key, "").strip()
	if value:
		return value

	if ENV_FILE.exists():
		load_dotenv(ENV_FILE)
	value = os.getenv(key, "").strip()
	if value:
		return value

	if default is not None:
		return default

	if ENV_FILE.exists():
		raise KeyError(f"{key} is not defined in {ENV_FILE.name} or the environment")

	raise KeyError(f"{key} is not defined in the environment")
