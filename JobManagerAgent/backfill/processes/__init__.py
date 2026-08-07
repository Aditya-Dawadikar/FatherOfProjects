"""Importing this package registers every built-in backfill process (see registry.py) as a
side effect of module import -- add a new process module here and import it below to make it
available to POST /backfill/run without touching engine.py or the API layer."""

from __future__ import annotations

from . import rescore_with_prompt  # noqa: F401
