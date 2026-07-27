#!/bin/sh
set -e

PORT="${PORT:-11434}"
export OLLAMA_HOST="0.0.0.0:${PORT}"
MODEL="${OLLAMA_MODEL:-llama3.1:8b}"

echo "Starting ollama serve on ${OLLAMA_HOST}"
ollama serve &
SERVE_PID=$!

trap 'kill -TERM "${SERVE_PID}" 2>/dev/null' TERM INT

echo "Waiting for ollama server to be ready..."
until ollama list >/dev/null 2>&1; do
	sleep 1
done

# No-op (fast local check, no re-download) if $MODEL is already present -- matters once a
# volume is attached at ollama's default data dir (/root/.ollama) so a restart/redeploy doesn't
# re-pull ~5GB every time.
echo "Pulling model ${MODEL} (skips the download if already present)..."
ollama pull "${MODEL}"

echo "Ollama ready, serving ${MODEL} on ${OLLAMA_HOST}"
wait "${SERVE_PID}"
