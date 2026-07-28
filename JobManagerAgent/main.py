from __future__ import annotations

import uvicorn

from api import create_app
from utils.env_utils import load_env_value


# Module-level `app` so this also works as `uvicorn main:app` (e.g. locally with --reload), not
# just `python main.py`. Kept as the entrypoint Dockerfile/railway.toml already invoke.
app = create_app()


if __name__ == "__main__":
	port = int(load_env_value("PORT", "8080"))
	uvicorn.run(app, host="0.0.0.0", port=port)
