from __future__ import annotations

import os


def main() -> None:
	backend_store_uri = os.environ["MLFLOW_BACKEND_STORE_URI"]
	artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT", "./mlruns")
	port = os.getenv("PORT", "5000")

	os.execvp(
		"mlflow",
		[
			"mlflow",
			"server",
			"--host", "0.0.0.0",
			"--port", port,
			"--backend-store-uri", backend_store_uri,
			"--artifacts-destination", artifact_root,
			"--serve-artifacts",
		],
	)


if __name__ == "__main__":
	main()
