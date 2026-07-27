from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DEFAULT_HEADERS = {
	"User-Agent": USER_AGENT,
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
	"Accept-Language": "en-US,en;q=0.9",
	"Cache-Control": "no-cache",
}
REQUEST_TIMEOUT_SECONDS = 30


class CrawlError(RuntimeError):
	pass


def fetch_html(url: str) -> str:
	try:
		response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
		response.raise_for_status()
	except RequestException as error:
		raise CrawlError(f"Failed to fetch {url}: {error}") from error
	return response.text


def extract_page_payload(html: str) -> dict[str, Any]:
	match = re.search(r'data-page="([^"]+)"', html)
	if match is None:
		raise CrawlError("Could not find the serialized page payload in the response")

	try:
		return json.loads(unescape(match.group(1)))
	except json.JSONDecodeError as error:
		raise CrawlError(f"Could not parse the serialized page payload: {error}") from error


def html_to_text(html_fragment: str | None) -> str:
	if not html_fragment:
		return ""
	soup = BeautifulSoup(html_fragment, "html.parser")
	return soup.get_text(separator="\n", strip=True)


def fetch_job_detail(job_url: str) -> dict[str, Any]:
	html = fetch_html(job_url)
	payload = extract_page_payload(html)
	job = payload.get("props", {}).get("job")
	if not isinstance(job, dict):
		raise CrawlError(f"No job payload found on page {job_url}")

	return {
		"title": job.get("title", ""),
		"description_text": html_to_text(job.get("descriptionHtml")),
		"interview_process_text": html_to_text(job.get("interviewProcessHtml")),
		"skills": job.get("skills") or [],
		"min_experience": job.get("minExperience"),
		"equity_range": job.get("equityRange"),
		"salary_range": job.get("salaryRange"),
		"sponsors_visa": job.get("sponsorsVisa"),
		"job_type": job.get("jobType"),
		"location": job.get("location"),
	}
