#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--env" && -n "$2" ]]; then
  ENV="$2"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +%Y-%m-%d-%H%M%S)
BACKUP_NAME="${TIMESTAMP}-${ENV}"
BACKUP_DIR="$SCRIPT_DIR/backups"
STAGING_DIR="/tmp/kms-backup-${BACKUP_NAME}"

mkdir -p "$BACKUP_DIR" "$STAGING_DIR"

# Determine vault source
if [[ "$ENV" == "prod" ]]; then
  VAULT_SRC="$SCRIPT_DIR/vault"
  COMPOSE_FILE="docker-compose.yml"
  VOLUME_NAME="knowledge-base_kb_data"
else
  VAULT_SRC="$SCRIPT_DIR/vault-test"
  COMPOSE_FILE="docker-compose.test.yml"
  VOLUME_NAME="knowledge-base_kb_data_test"
fi

echo "Backing up KMS ($ENV) to backups/${BACKUP_NAME}.tar.gz ..."

# 1. Copy vault files
cp -r "$VAULT_SRC" "$STAGING_DIR/vault"

# 2. Dump SQLite DB from Docker volume
docker run --rm \
  -v "${VOLUME_NAME}:/data:ro" \
  -v "${STAGING_DIR}:/backup" \
  busybox \
  cp /data/kb.db /backup/kb.db

# 3. Dump ChromaDB from Docker volume
docker run --rm \
  -v "${VOLUME_NAME}:/data:ro" \
  -v "${STAGING_DIR}:/backup" \
  busybox \
  sh -c "cp -r /data/chroma /backup/chroma 2>/dev/null || true"

# 4. Create archive
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C /tmp "kms-backup-${BACKUP_NAME}"
rm -rf "$STAGING_DIR"

echo "Backup saved: backups/${BACKUP_NAME}.tar.gz"

# 5. Keep only last 10 backups
ls -t "${BACKUP_DIR}"/*.tar.gz 2>/dev/null | tail -n +11 | xargs -r rm -f
echo "Done."
