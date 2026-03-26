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
echo "Step 1/6: Backing up test data..."
./backup.sh --env test
echo ""
echo "Step 2/6: Backup complete."
read -r -p "Continue with deployment? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Deployment aborted."
  exit 1
fi

echo ""
echo "Step 3/6: Exporting user accounts..."
docker compose -f docker-compose.test.yml --env-file .env.test exec api python manage.py export-users --output /data/manage/users.json

echo ""
echo "Step 4/6: Pulling latest code from branch '$BRANCH'..."
git pull origin "$BRANCH"

echo ""
echo "Step 5/6: Rebuilding and restarting test stack..."
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
docker compose -f docker-compose.test.yml --env-file .env.test build api ui
docker compose -f docker-compose.test.yml --env-file .env.test up -d

echo ""
echo "Step 6/6: Waiting for API to be ready..."
HEALTHY=0
for i in $(seq 1 30); do
  if curl -sf http://localhost:8081/kms/api/health > /dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 2
done
if [[ $HEALTHY -eq 0 ]]; then
  echo "ERROR: API did not become healthy after 60 seconds. User import skipped."
  echo "Run manually: docker compose -f docker-compose.test.yml --env-file .env.test exec api python manage.py import-users --input /data/manage/users.json"
  exit 1
fi
docker compose -f docker-compose.test.yml --env-file .env.test exec api python manage.py import-users --input /data/manage/users.json

echo ""
echo "Deployment complete. KMS test running at http://localhost:8081/kms"
