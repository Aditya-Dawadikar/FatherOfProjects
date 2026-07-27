from __future__ import annotations

import os
import sys


def _as_bool(value: str | None) -> bool:
	if value is None:
		return False
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _collect_allowed_hosts(port: str) -> str | None:
	explicit = os.getenv("MLFLOW_ALLOWED_HOSTS", "").strip()
	if explicit:
		return explicit

	# Railway injects these automatically; use them so the server accepts its own
	# public/internal domains without extra config. RAILWAY_PUBLIC_DOMAIN is only set
	# once the service has a public domain generated.
	hosts: list[str] = []
	public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
	if public_domain:
		hosts.append(public_domain)

	private_domain = os.getenv("RAILWAY_PRIVATE_DOMAIN", "").strip()
	if private_domain:
		hosts.append(private_domain)
		hosts.append(f"{private_domain}:{port}")

	# Railway public domains are under *.up.railway.app; include wildcard for
	# custom/generated subdomains that may differ from injected env values.
	hosts.extend(["*.up.railway.app", "*.railway.internal"])

	# Local access for development / SSH tunnel checks.
	hosts.extend(["localhost", "127.0.0.1", "::1"])

	return ",".join(hosts) if hosts else None


def _collect_cors_allowed_origins() -> str | None:
	explicit = os.getenv("MLFLOW_CORS_ALLOWED_ORIGINS", "").strip()
	if explicit:
		return explicit

	origins: list[str] = [
		"http://localhost:5000",
		"http://127.0.0.1:5000",
	]

	public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
	if public_domain:
		origins.extend([f"https://{public_domain}", f"http://{public_domain}"])

	private_domain = os.getenv("RAILWAY_PRIVATE_DOMAIN", "").strip()
	if private_domain:
		origins.extend([f"http://{private_domain}", f"https://{private_domain}"])

	# Broad Railway defaults for API calls coming from MLflow UI hosted on Railway.
	origins.extend(["https://*.up.railway.app", "http://*.up.railway.app"])

	return ",".join(origins)


def main() -> None:
	backend_store_uri = os.environ["MLFLOW_BACKEND_STORE_URI"]
	artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT", "./mlruns")
	port = os.getenv("PORT", "5000")

	args = [
		sys.executable,
		"-m", "mlflow",
		"server",
		"--host", "0.0.0.0",
		"--port", port,
		"--backend-store-uri", backend_store_uri,
		"--artifacts-destination", artifact_root,
		"--serve-artifacts",
	]

	allowed_hosts = _collect_allowed_hosts(port)
	if allowed_hosts:
		args += ["--allowed-hosts", allowed_hosts]

	cors_allowed_origins = _collect_cors_allowed_origins()
	if cors_allowed_origins:
		args += ["--cors-allowed-origins", cors_allowed_origins]

	if _as_bool(os.getenv("MLFLOW_DISABLE_SECURITY_MIDDLEWARE")):
		args.append("--disable-security-middleware")

	os.execv(sys.executable, args)


if __name__ == "__main__":
	main()
