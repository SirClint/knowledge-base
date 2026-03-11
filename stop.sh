#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--test" ]]; then
  ENV="test"
fi

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
if [[ "$ENV" == "test" ]]; then
  COMPOSE_FILE="docker-compose.test.yml"
  ENV_FILE=".env.test"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping KMS ($ENV)..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down || true

# Only kill Ollama if stopping prod (don't kill if test might still use it)
if [[ "$ENV" == "prod" ]]; then
  OLLAMA_PID_FILE="/tmp/ollama-kms.pid"
  if [[ -f "$OLLAMA_PID_FILE" ]]; then
    PID=$(cat "$OLLAMA_PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      echo "Stopping Ollama (pid $PID)..."
      kill "$PID"
    fi
    rm -f "$OLLAMA_PID_FILE"
  fi
fi

echo "KMS ($ENV) stopped."
