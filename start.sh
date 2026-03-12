#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--test" ]]; then
  ENV="test"
fi

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
PORT=8080
if [[ "$ENV" == "test" ]]; then
  COMPOSE_FILE="docker-compose.test.yml"
  ENV_FILE=".env.test"
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

# Verify Ollama is reachable from Docker containers
echo "Checking Ollama is reachable from Docker..."
DOCKER_GATEWAY=$(docker network inspect bridge --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null || echo "")
OLLAMA_DOCKER_OK=0
if [[ -n "$DOCKER_GATEWAY" ]]; then
  if curl -sf "http://${DOCKER_GATEWAY}:11434/api/tags" > /dev/null 2>&1; then
    OLLAMA_DOCKER_OK=1
  fi
fi
if [[ "$OLLAMA_DOCKER_OK" -eq 0 ]]; then
  echo ""
  echo "WARNING: Ollama is not reachable from Docker containers."
  echo "AI features will show as offline in the UI."
  echo ""
  echo "To fix:"
  echo "  1. Ensure Ollama binds to all interfaces:"
  echo "     sudo sh -c 'mkdir -p /etc/systemd/system/ollama.service.d && echo \"[Service]\nEnvironment=\\\"OLLAMA_HOST=0.0.0.0\\\"\" > /etc/systemd/system/ollama.service.d/override.conf'"
  echo "     sudo systemctl daemon-reload && sudo systemctl restart ollama"
  echo "  2. Allow Docker bridge through firewall:"
  echo "     sudo ufw allow in on docker0 to any port 11434"
  echo "  3. Re-run: ./start.sh"
  echo ""
fi

# Start Docker stack
echo "Starting KMS ($ENV) on port $PORT..."
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Open browser (try common Linux methods, then macOS)
URL="http://localhost:$PORT/kms"
echo "Opening $URL"
if command -v xdg-open &>/dev/null; then
  xdg-open "$URL" & disown
elif command -v open &>/dev/null; then
  open "$URL"
fi

echo "KMS ($ENV) started at $URL"
