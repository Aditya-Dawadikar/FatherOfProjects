from __future__ import annotations

import re
from typing import Any

from utils.config import GUARDRAIL_INJECTION_PATTERNS

from .errors import GuardrailBlockedError


_COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in GUARDRAIL_INJECTION_PATTERNS]

# The only job fields render_prompt() (llm_providers/base.py) interpolates as free text of any
# real length -- title is short and mostly attacker-uncontrolled noise, but included since it's
# still scraped, untrusted text.
_SCANNED_FIELDS = ("description_text", "interview_process_text", "title")


def scan_job_for_injection(*, job_id: int | None, job: dict[str, Any]) -> None:
	"""Screens a crawled job posting for prompt-injection attempts before it's interpolated into
	the scoring prompt. Job postings are scraped from the open web and rendered straight into the
	LLM's input by render_prompt() -- untrusted in a way the resume (supplied by the candidate
	running the agent, not the internet) is not.
	"""
	haystack = " ".join(str(job.get(field) or "") for field in _SCANNED_FIELDS)
	for pattern in _COMPILED_PATTERNS:
		match = pattern.search(haystack)
		if match:
			raise GuardrailBlockedError(
				guardrail="prompt_injection",
				category="injection",
				job_id=job_id,
				reason=(
					f"job_id={job_id}: job content matched injection pattern {pattern.pattern!r} "
					f"near {match.group(0)!r}"
				),
			)
