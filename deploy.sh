#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  KMS Production Deployment"
echo "======================================"
echo ""
echo "Step 1/6: Backing up production data..."
./backup.sh --env prod
echo ""
echo "Step 2/6: Backup complete."
read -r -p "Continue with deployment? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Deployment aborted."
  exit 1
fi

echo ""
echo "Step 3/6: Exporting user accounts..."
docker compose --env-file .env exec api python manage.py export-users --output /data/manage/users.json

echo ""
echo "Step 4/6: Pulling latest code from main..."
git fetch origin main
git checkout main
git reset --hard origin/main

echo ""
echo "Step 5/6: Rebuilding and restarting production stack..."
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
docker compose --env-file .env build api ui
docker compose --env-file .env up -d

echo ""
echo "Step 6/6: Waiting for API to be ready..."
HEALTHY=0
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/kms/api/health > /dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 2
done
if [[ $HEALTHY -eq 0 ]]; then
  echo "ERROR: API did not become healthy after 60 seconds. User import skipped."
  echo "Run manually: docker compose --env-file .env exec api python manage.py import-users --input /data/manage/users.json"
  exit 1
fi
docker compose --env-file .env exec api python manage.py import-users --input /data/manage/users.json

echo ""
echo "Deployment complete. KMS prod running at http://localhost:8080/kms"
