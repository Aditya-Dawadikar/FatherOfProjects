# MLflow Server

Standalone MLflow Tracking Server, backed by Postgres. `JobManagerAgent` points its
`MLFLOW_TRACKING_URI` at this service's URL so registered prompt versions (and any future
experiment/run logging) persist in one place instead of a per-service local SQLite file.

## Setup

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`:
- `MLFLOW_BACKEND_STORE_URI` — a Postgres URL. Can be the same instance WebScraper/JobDataServer
  use (MLflow creates its own tables — `registered_models`, `model_versions`, `experiments`,
  etc. — with no collision) or a dedicated database.
- `MLFLOW_ARTIFACT_ROOT` — local disk by default. Not used by the prompt registry (prompts are
  metadata-only), so the default is fine unless you start logging real run artifacts.

Run locally:

```powershell
venv\Scripts\python serve.py
```

The UI is served at `http://localhost:5000`.

## Deploying

New Railway service pointed at this directory, same shape as the other Python services here
(`Dockerfile` + `railway.toml`). Set `MLFLOW_BACKEND_STORE_URI` in the service's variables.

**Security note:** this server has no authentication in front of it. Prefer Railway's private
networking (reach it from `JobManagerAgent` via its `*.railway.internal` address) over
generating a public domain for it. If you do need external access to the UI, put it behind a
reverse proxy with auth, or add MLflow's basic-auth app (`mlflow[auth]`) as a follow-up.

## Using it from JobManagerAgent

Set `JobManagerAgent`'s `MLFLOW_TRACKING_URI` to this server's URL (e.g. its Railway internal
address) instead of a local `sqlite:///./mlflow.db` file — no code changes needed, MLflow's
client talks to a remote tracking server transparently over the same API.
