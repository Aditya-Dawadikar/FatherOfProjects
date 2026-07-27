# Ollama Server

Self-hosted [Ollama](https://ollama.com) instance serving a local LLM, so `JobManagerAgent` can
score job matches (`LLM_PROVIDER=ollama`) without depending on a paid/quota-limited hosted API
(Groq, Gemini). Same shape as the other standalone services here (`Dockerfile` + `railway.toml`),
but built from Ollama's own image instead of a Python base — there's no `requirements.txt` to
install from, so `railway.toml` uses `builder = "dockerfile"` instead of the `railpack` builder
every other service in this repo uses.

## What it does on boot

`start.sh` (the container's entrypoint):
1. Binds `ollama serve` to `0.0.0.0:$PORT` (Railway injects `PORT`; defaults to `11434` locally)
   instead of ollama's own default of `127.0.0.1:11434`, so other services can reach it over
   Railway's private network.
2. Waits for the server to come up (`ollama list` succeeding).
3. Runs `ollama pull $OLLAMA_MODEL` (default `llama3.1:8b`) — a fast no-op if that model is
   already present (see "Persisting the model" below), otherwise a ~5GB download.
4. Waits on the `ollama serve` process, keeping the container alive.

## Resource requirements — read before deploying

This is a real, unquantized-by-default 8B-parameter model running on CPU (Railway doesn't offer
GPU instances at the time of writing). Concretely, for `llama3.1:8b` at its default `Q4_K_M`
quantization:
- **Disk**: ~5GB for the model weights.
- **RAM**: plan for 6-8GB headroom; the process will OOM well below that if the service's memory
  limit is set too low.
- **CPU**: inference will be noticeably slower than a hosted API (Groq/Gemini) — seconds per
  response rather than sub-second. `JobManagerAgent` already paces one call at a time with
  `LLM_REQUEST_DELAY_SECONDS` between jobs, so slower-but-steady is tolerable for this use case;
  it would not be for a latency-sensitive one.
- **Cost**: whatever Railway plan you're on needs to actually support that RAM/CPU footprint
  running continuously — check your plan's limits before deploying, not after it OOM-crashes in
  a loop.

If any of that doesn't fit your plan, a smaller/lighter-quantized model (see `OLLAMA_MODEL` in
`.env.example`) or a hosted provider (`LLM_PROVIDER=groq`/`gemini`) are the fallbacks.

## Persisting the model

Without a volume, every redeploy or restart re-runs `ollama pull` against an empty container
filesystem — a ~5GB re-download each time. Attach a Railway volume to this service (mounted at,
say, `/data`) and set `OLLAMA_MODELS=/data` so pulled weights survive redeploys:

```powershell
railway volume add --mount-path /data --service OllamaServer
railway variables --set OLLAMA_MODELS=/data --service OllamaServer
```

## Setup (local)

```powershell
docker build -t ollama-server .
copy .env.example .env
docker run --rm -p 11434:11434 --env-file .env ollama-server
```

Or without Docker, if you already have [Ollama installed locally](https://ollama.com/download):

```powershell
ollama pull llama3.1:8b
ollama serve
```

## Using it from JobManagerAgent

Set `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL` to this service's address — its Railway internal
address in production (e.g. `http://ollamaserver.railway.internal:11434`), or
`http://localhost:11434` for local dev. See `JobManagerAgent/README.md`'s "LLM provider" section
for the full provider abstraction this plugs into.
