#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--test" ]]; then
  ENV="test"
fi

COMPOSE_FILE="docker-compose.yml"
PORT=8080
if [[ "$ENV" == "test" ]]; then
  COMPOSE_FILE="docker-compose.test.yml"
  PORT=8081
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OLLAMA_PID_FILE="/tmp/ollama-kms.pid"

# Start Ollama if not already running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
  echo "Starting Ollama..."
  OLLAMA_HOST=0.0.0.0 ollama serve &>/tmp/ollama-kms.log &
  echo $! > "$OLLAMA_PID_FILE"
  # Wait up to 10 seconds for Ollama to be ready
  OLLAMA_READY=0
  for i in $(seq 1 10); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
      echo "Ollama is ready."
      OLLAMA_READY=1
      break
    fi
    sleep 1
  done
  if [[ "$OLLAMA_READY" -eq 0 ]]; then
    echo "Warning: Ollama did not respond within 10 seconds. AI features may be unavailable."
    echo "Check /tmp/ollama-kms.log for details."
  fi
else
  echo "Ollama is already running."
fi

# Start Docker stack
echo "Starting KMS ($ENV) on port $PORT..."
docker compose -f "$COMPOSE_FILE" up -d

# Open browser (try common Linux methods, then macOS)
URL="http://localhost:$PORT/kms"
echo "Opening $URL"
if command -v xdg-open &>/dev/null; then
  xdg-open "$URL" &
elif command -v open &>/dev/null; then
  open "$URL"
fi

echo "KMS ($ENV) started at $URL"
