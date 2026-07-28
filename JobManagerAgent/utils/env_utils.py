from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# Anchored off this file's own location (utils/env_utils.py -> JobManagerAgent/), not
# with_name(), which broke when this module moved into utils/ during the package reorg and kept
# resolving to a nonexistent utils/.env. Computed locally rather than imported from
# utils/config.py -- config.py itself imports load_env_value from here, so the reverse would be
# circular.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


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
