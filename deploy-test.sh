#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "======================================"
echo "  KMS Test Deployment"
echo "  Branch: $BRANCH"
echo "======================================"
echo ""
echo "Step 1/4: Backing up test data..."
./backup.sh --env test
echo ""
echo "Step 2/4: Backup complete."
read -r -p "Continue with deployment? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Deployment aborted."
  exit 1
fi

echo ""
echo "Step 3/4: Pulling latest code from branch '$BRANCH'..."
git pull origin "$BRANCH"

echo ""
echo "Step 4/4: Rebuilding and restarting test stack..."
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
docker compose -f docker-compose.test.yml --env-file .env.test build api ui
docker compose -f docker-compose.test.yml --env-file .env.test up -d

echo ""
echo "Deployment complete. KMS test running at http://localhost:8081/kms"
