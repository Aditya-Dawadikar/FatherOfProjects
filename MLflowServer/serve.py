from __future__ import annotations

import os
import sys


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

	return ",".join(hosts) if hosts else None


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

	os.execv(sys.executable, args)


if __name__ == "__main__":
	main()
