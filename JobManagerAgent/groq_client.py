from __future__ import annotations

import json
import logging
import re
from typing import Any

from groq import Groq

from env_utils import load_env_value


LOGGER = logging.getLogger(__name__)
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class MatchResponseError(RuntimeError):
	pass


def load_groq_model() -> str:
	return load_env_value("GROQ_MODEL", DEFAULT_GROQ_MODEL)


def build_client() -> Groq:
	return Groq(api_key=load_env_value("GROQ_API_KEY"))


def _text_or_blank(value: Any) -> str:
	return "" if value is None else str(value)


def render_prompt(prompt_version: Any, *, resume: str, job: dict[str, Any]) -> str:
	skills = job.get("skills") or []
	return prompt_version.format(
		resume=resume,
		job_title=job.get("title") or "",
		company_name=job.get("company_name") or "",
		location=job.get("location") or "",
		job_type=job.get("job_type") or "",
		min_experience=_text_or_blank(job.get("min_experience")),
		salary_range=job.get("salary_range") or "",
		equity_range=job.get("equity_range") or "",
		sponsors_visa=_text_or_blank(job.get("sponsors_visa")),
		skills=", ".join(skills) if skills else "",
		description_text=job.get("description_text") or "",
		interview_process_text=job.get("interview_process_text") or "",
	)


def _extract_json_object(text: str) -> dict[str, Any]:
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		pass

	match = re.search(r"\{.*\}", text, re.DOTALL)
	if match is None:
		raise MatchResponseError(f"Model response did not contain a JSON object: {text[:200]!r}")

	try:
		return json.loads(match.group(0))
	except json.JSONDecodeError as error:
		raise MatchResponseError(f"Model response JSON could not be parsed: {error}") from error


def parse_match_response(text: str) -> dict[str, Any]:
	parsed = _extract_json_object(text)

	score = parsed.get("match_score")
	if not isinstance(score, (int, float)):
		raise MatchResponseError(f"Model response missing numeric match_score: {parsed!r}")
	clamped_score = max(0, min(100, int(round(score))))

	reasoning = str(parsed.get("reasoning") or "").strip()

	return {"match_score": clamped_score, "reasoning": reasoning}


def evaluate_match(client: Groq, *, model: str, prompt: str) -> dict[str, Any]:
	response = client.chat.completions.create(
		model=model,
		messages=[{"role": "user", "content": prompt}],
		temperature=0,
		response_format={"type": "json_object"},
	)
	content = response.choices[0].message.content or ""
	return parse_match_response(content)
