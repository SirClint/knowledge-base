#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  KMS Production Deployment"
echo "======================================"
echo ""
echo "Step 1/4: Backing up production data..."
./backup.sh --env prod
echo ""
echo "Step 2/4: Backup complete."
read -r -p "Continue with deployment? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Deployment aborted."
  exit 1
fi

echo ""
echo "Step 3/4: Pulling latest code from main..."
git pull origin main

echo ""
echo "Step 4/4: Rebuilding and restarting production stack..."
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
docker compose build api ui
docker compose up -d

echo ""
echo "Deployment complete. KMS prod running at http://localhost:8080/kms"
