from __future__ import annotations

import json
import os
import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv
from requests.exceptions import HTTPError, RequestException


ENV_FILE = Path(__file__).with_name(".env")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
BASE_URL = "https://www.workatastartup.com"
DEFAULT_HEADERS = {
	"User-Agent": USER_AGENT,
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
	"Accept-Language": "en-US,en;q=0.9",
	"Cache-Control": "no-cache",
	"Pragma": "no-cache",
	"Upgrade-Insecure-Requests": "1",
	"Sec-Fetch-Dest": "document",
	"Sec-Fetch-Mode": "navigate",
	"Sec-Fetch-Site": "none",
	"Sec-Fetch-User": "?1",
}


def load_env_value(key: str) -> str:
	value = os.getenv(key, "").strip()
	if value:
		return value

	if ENV_FILE.exists():
		load_dotenv(ENV_FILE)
	value = os.getenv(key, "").strip()
	if value:
		return value

	if ENV_FILE.exists():
		raise KeyError(f"{key} is not defined in {ENV_FILE.name} or the environment")

	raise KeyError(f"{key} is not defined in the environment")


def fetch_html(url: str) -> str:
	response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
	response.raise_for_status()
	return response.text


def extract_page_payload(html: str) -> dict[str, Any]:
	match = re.search(r'data-page="([^"]+)"', html)
	if match is None:
		raise ValueError("Could not find the serialized page payload in the response")

	return json.loads(unescape(match.group(1)))


def parse_job(job: dict[str, Any]) -> dict[str, Any]:
	job_id = job.get("id")
	company_slug = job.get("companySlug", "")
	job_url = urljoin(BASE_URL, f"/jobs/{job_id}") if job_id else ""
	company_url = urljoin(BASE_URL, f"/companies/{company_slug}") if company_slug else ""

	return {
		"company_name": job.get("companyName", ""),
		"company_batch": job.get("companyBatch", ""),
		"company_url": company_url,
		"company_one_liner": job.get("companyOneLiner", ""),
		"company_logo_url": job.get("companyLogoUrl", ""),
		"company_last_active_at": job.get("companyLastActiveAt", ""),
		"job_id": job_id,
		"job_role": job.get("title", ""),
		"job_url": job_url,
		"application_link": job.get("applyUrl", ""),
		"location": job.get("location", ""),
		"job_type": job.get("jobType", ""),
		"role_type": job.get("roleType", ""),
		"salary_range": job.get("salary", ""),
	}


def scrape(url: str) -> dict[str, Any]:
	html = fetch_html(url)
	payload = extract_page_payload(html)
	jobs_payload = payload.get("props", {}).get("jobs", [])
	jobs = [parse_job(job) for job in jobs_payload]

	return {
		"url": url,
		"html_length": len(html),
		"job_count": len(jobs),
		"jobs": jobs,
	}


def run_scrape_stage(target_url: str | None = None) -> dict[str, Any]:
	resolved_target_url = target_url or load_env_value("TARGET_URL")
	return scrape(resolved_target_url)


def main() -> None:
	result = run_scrape_stage()

	print(f"Scraped: {result['url']}")
	print(f"HTML size: {result['html_length']} characters")
	print(f"Jobs found: {result['job_count']}")
	print(json.dumps(result["jobs"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
	try:
		main()
	except KeyError as error:
		raise SystemExit(f"Configuration error: {error}") from error
	except FileNotFoundError as error:
		raise SystemExit(str(error)) from error
	except HTTPError as error:
		status_code = error.response.status_code if error.response is not None else "unknown"
		raise SystemExit(f"HTTP error {status_code}: {error}") from error
	except RequestException as error:
		raise SystemExit(f"Request failed: {error}") from error
