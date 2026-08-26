from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

from utils.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT


EMPTY_JOB_DETAIL: dict[str, Any] = {
	"title": "",
	"description_text": "",
	"interview_process_text": "",
	"skills": [],
	"min_experience": None,
	"equity_range": None,
	"salary_range": None,
	"sponsors_visa": None,
	"job_type": None,
	"location": None,
}


DEFAULT_HEADERS = {
	"User-Agent": USER_AGENT,
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
	"Accept-Language": "en-US,en;q=0.9",
	"Cache-Control": "no-cache",
}


class CrawlError(RuntimeError):
	pass


class NotFoundCrawlError(CrawlError):
	def __init__(self, url: str):
		super().__init__(f"Job page not found: {url}")
		self.url = url


def fetch_html(url: str) -> str:
	try:
		response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
		response.raise_for_status()
	except requests.HTTPError as error:
		if error.response is not None and error.response.status_code == 404:
			raise NotFoundCrawlError(url) from error
		raise CrawlError(f"Failed to fetch {url}: {error}") from error
	except RequestException as error:
		raise CrawlError(f"Failed to fetch {url}: {error}") from error
	return response.text


def fetch_json(url: str) -> Any:
	try:
		response = requests.get(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
		response.raise_for_status()
	except requests.HTTPError as error:
		if error.response is not None and error.response.status_code == 404:
			raise NotFoundCrawlError(url) from error
		raise CrawlError(f"Failed to fetch {url}: {error}") from error
	except RequestException as error:
		raise CrawlError(f"Failed to fetch {url}: {error}") from error
	try:
		return response.json()
	except ValueError as error:
		raise CrawlError(f"Could not parse JSON from {url}: {error}") from error


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


def fetch_job_detail_greenhouse(job_url: str) -> dict[str, Any]:
	"""job_url is WebScraper's stored Greenhouse Job Board API detail endpoint for this specific
	posting (`https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{id}?content=true`,
	confirmed live against boards-api.greenhouse.io/v1/boards/stripe/jobs/... during development) --
	a plain JSON GET, no HTML page parsing needed. `content` comes back HTML-escaped (literal
	`&lt;h2&gt;` etc.) on top of being itself an HTML fragment, so it needs unescaping before
	html_to_text can strip the tags.
	"""
	job = fetch_json(job_url)
	if not isinstance(job, dict):
		raise CrawlError(f"Unexpected Greenhouse job payload at {job_url}")

	return {
		**EMPTY_JOB_DETAIL,
		"title": job.get("title", ""),
		"description_text": html_to_text(unescape(job.get("content") or "")),
		"location": (job.get("location") or {}).get("name"),
	}


def fetch_job_detail_ashby(job_url: str, source_job_id: str) -> dict[str, Any]:
	"""job_url is WebScraper's stored Ashby public Job Board API list endpoint for this company
	(`https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true`,
	confirmed live during development) -- unlike Greenhouse there is no separate per-job detail
	endpoint, so the whole board is re-fetched and filtered down to `source_job_id` (Ashby's UUID
	job id). Confirmed live that this list response already includes full `descriptionHtml` per
	job, so no further request is needed once the matching entry is found.
	"""
	payload = fetch_json(job_url)
	jobs = (payload or {}).get("jobs") or []
	job = next((j for j in jobs if j.get("id") == source_job_id), None)
	if job is None:
		raise NotFoundCrawlError(job_url)

	return {
		**EMPTY_JOB_DETAIL,
		"title": job.get("title", ""),
		"description_text": html_to_text(job.get("descriptionHtml")) or (job.get("descriptionPlain") or ""),
		"job_type": job.get("employmentType"),
		"location": job.get("location"),
	}


def fetch_job_detail_lever(job_url: str, source_job_id: str) -> dict[str, Any]:
	"""job_url is WebScraper's stored Lever postings API list endpoint for this company
	(`https://api.lever.co/v0/postings/{company}?mode=json`, confirmed live during development) --
	like Ashby, the whole board is re-fetched and filtered down to `source_job_id` (Lever's UUID
	posting id); the list response already carries full descriptionPlain/lists content per posting.
	"""
	jobs = fetch_json(job_url)
	if not isinstance(jobs, list):
		raise CrawlError(f"Unexpected Lever postings payload at {job_url}")
	job = next((j for j in jobs if j.get("id") == source_job_id), None)
	if job is None:
		raise NotFoundCrawlError(job_url)

	sections = job.get("lists") or []
	section_text = "\n\n".join(
		f"{section.get('text', '')}\n{html_to_text(section.get('content'))}" for section in sections
	)
	description = job.get("descriptionPlain") or html_to_text(job.get("description"))
	categories = job.get("categories") or {}

	return {
		**EMPTY_JOB_DETAIL,
		"title": job.get("text", ""),
		"description_text": "\n\n".join(part for part in (description, section_text) if part),
		"job_type": categories.get("commitment"),
		"location": categories.get("location"),
	}


def fetch_job_detail_for_source(source: str, job_url: str, source_job_id: str) -> dict[str, Any]:
	"""Dispatch to the right per-source detail fetcher -- the one thing services/crawler.py
	previously assumed was always workatastartup's `data-page` HTML blob. Each fetcher's docstring
	notes exactly what job_url is expected to contain for that source (WebScraper is responsible
	for storing the right shape when it writes a row -- see WebScraper's per-source fetchers)."""
	if source == "greenhouse":
		return fetch_job_detail_greenhouse(job_url)
	if source == "ashby":
		return fetch_job_detail_ashby(job_url, source_job_id)
	if source == "lever":
		return fetch_job_detail_lever(job_url, source_job_id)
	return fetch_job_detail(job_url)
