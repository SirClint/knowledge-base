# KMS Deployment Guide

## Environments

| Environment | URL | Compose file | Vault | Data volumes |
|---|---|---|---|---|
| **Production** | http://localhost:8080/kms | `docker-compose.yml` | `vault/` | `kb_data`, `caddy_data` |
| **Test** | http://localhost:8081/kms | `docker-compose.test.yml` | `vault-test/` | `kb_data_test`, `caddy_data_test` |

Environments are fully isolated — separate databases, separate vault directories, separate Docker volumes. Test data never touches production.

---

## One-Time Host Setup

These steps are required once on a new machine before the application will work correctly.

### 1. Ollama binding
Ollama must listen on all interfaces (not just localhost) so Docker containers can reach it:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo sh -c 'echo "[Service]\nEnvironment=\"OLLAMA_HOST=0.0.0.0\"" > /etc/systemd/system/ollama.service.d/override.conf'
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

### 2. UFW firewall rule
Allow Docker containers to reach Ollama on the host. This is a subnet-based rule — set it once and it survives all Docker network recreates:

```bash
sudo ufw allow from 172.18.0.0/16 to any port 11434
```

Verify with `sudo ufw status` — you should see one rule:
```
11434    ALLOW IN    172.18.0.0/16
```

---

## Starting and Stopping

```bash
./start.sh          # start production (opens browser at http://localhost:8080/kms)
./start.sh --test   # start test environment (opens browser at http://localhost:8081/kms)

./stop.sh           # stop production (also stops Ollama if started by this script)
./stop.sh --test    # stop test environment (leaves Ollama running)
```

Desktop launchers (`kms.desktop`, `kms-test.desktop`) in the project root can be copied to `~/Desktop` for one-click startup.

---

## Development Workflow

```
feature branch → test environment → deploy-test → PR to main → deploy to prod
```

1. **Create a feature branch** and develop your changes
2. **Start the test environment**: `./start.sh --test`
3. **Test your changes** manually at http://localhost:8081/kms
4. **Run the test deploy** to verify the deploy process itself works: `./deploy-test.sh`
   - Backs up test data, confirms, pulls current branch, rebuilds, restarts test stack
5. **Commit and push** your branch, open a Pull Request on GitHub
6. **Merge the PR** to `main` after review
7. **Deploy to production**: `./deploy.sh`

### deploy-test.sh vs deploy.sh

| | `deploy-test.sh` | `deploy.sh` |
|---|---|---|
| Target | Test (port 8081) | Production (port 8080) |
| Branch pulled | Current branch | `main` |
| Backup | `--env test` | `--env prod` |
| Purpose | Verify the deploy process safely | Ship to production |

---

## Deploying to Production

Run `./deploy.sh` from the project root. It enforces these six steps — **none can be skipped**:

### Step 1: Automatic backup
`./backup.sh --env prod` runs automatically. It archives:
- All vault markdown files (`vault/`)
- The SQLite database (`kb.db`) from the Docker volume
- ChromaDB vector data

The archive is saved to `backups/YYYY-MM-DD-HHMMSS-prod.tar.gz`. If the backup fails for any reason (disk full, Docker not running, etc.), the script aborts and production is never touched.

### Step 2: Human confirmation
You are shown the backup file path and asked to type `yes` to continue. Type anything else (or Ctrl+C) to abort — no changes have been made yet.

### Step 3: Export user accounts
All user accounts are exported to `/data/manage/users.json` inside the `kb_data` Docker volume. This file persists across image rebuilds and is used to restore accounts after the new containers start.

### Step 4: Pull latest code
`git pull origin main` fetches the latest merged code. If there are conflicts or the pull fails, the script aborts.

### Step 5: Rebuild and restart
```
docker compose build api ui
docker compose up -d
```
Both the API and UI containers are rebuilt from source, then restarted. The database and vault data are preserved (they live in Docker volumes and the `vault/` directory, not in the container images).

### Step 6: Wait for API health and import user accounts
The script polls the API health endpoint for up to 60 seconds. Once the API is healthy, it imports any users from the export file that don't already exist in the database. If the API never becomes healthy within the timeout, the script exits with an error and prints the recovery command to run the import manually.

---

## Backups

### Manual backup (run anytime)
```bash
./backup.sh               # backs up production (default)
./backup.sh --env prod    # same as above, explicit
./backup.sh --env test    # backs up test environment
```

Archives are saved to `backups/` and the last 10 are kept automatically (older ones are deleted).

### When to run a backup manually
- **Before any destructive action** — wiping volumes, resetting the database, deleting large amounts of content
- **Before major testing** on production
- The deploy script runs a backup automatically, so you don't need to run one separately before deploying

### Restoring from a backup
```bash
# 1. Stop the stack
./stop.sh

# 2. Extract the archive
tar -xzf backups/YYYY-MM-DD-HHMMSS-prod.tar.gz -C /tmp

# 3. Restore vault files
cp -r /tmp/kms-backup-*/vault/* vault/

# 4. Restore the database (copy into the Docker volume)
docker run --rm \
  -v knowledge-base_kb_data:/data \
  -v /tmp/kms-backup-YYYY-MM-DD-HHMMSS-prod:/backup:ro \
  busybox cp /backup/kb.db /data/kb.db

# 5. Restart
./start.sh
```

---

## Account Management

### Creating the initial admin account

After a fresh install or if the database volume is wiped, no user accounts exist. Since the application locks self-registration to the `reader` role, you must create the first admin account from the command line:

```bash
# Test environment
make create-admin email=your@email.com password=YourPassword

# Production environment (make targets are test-only — run directly for prod)
docker compose --env-file .env exec api python manage.py create-admin \
  --email your@email.com --password YourPassword
```

If the account already exists, the command exits cleanly: `User already exists: <email>`.

### Automatic account preservation during deploys

Both `deploy.sh` and `deploy-test.sh` automatically preserve user accounts across image rebuilds:

1. **Before rebuild** — exports all user accounts to `/data/manage/users.json` inside the data volume
2. **After restart** — waits for the API to become healthy, then imports any users from the export file that don't already exist in the database

This happens automatically on every deploy — no manual steps required. The export file survives image rebuilds because it lives inside the `kb_data` Docker volume, which is not removed during a normal deploy.

> **Note:** This does not protect against Docker volume removal (`docker volume rm` or `docker compose down -v`). If a volume is wiped, restore from a `backup.sh` archive — see "Restoring from a backup" above.

### Manual export and import

To export or import users manually (e.g., to recover from an issue):

```bash
# Test environment
make export-users    # writes /data/manage/users.json inside the container volume
make import-users    # reads /data/manage/users.json, skips already-existing users

# Production environment
docker compose --env-file .env exec api python manage.py export-users --output /data/manage/users.json
docker compose --env-file .env exec api python manage.py import-users --input /data/manage/users.json
```

---

## Resetting an Environment (Wipe All Data)

> ⚠️ **Always back up first**, even if the data looks like test data.

```bash
# Back up first
./backup.sh --env prod    # or --env test

# Stop the stack
./stop.sh                 # or ./stop.sh --test

# Remove volumes (wipes database and ChromaDB)
docker volume rm knowledge-base_kb_data knowledge-base_caddy_data
# For test: docker volume rm knowledge-base_kb_data_test knowledge-base_caddy_data_test

# Clear vault files
rm -rf vault/personal/* vault/team/processes/* vault/team/architecture/* vault/team/projects/*
# For test: rm -rf vault-test/personal/* ...

# Restart fresh
./start.sh                # or ./start.sh --test
```

---

## Mailgun Email Ingestion Setup

See `docs/plans/2026-03-08-version-history-comments-email-ingestion-plan.md` → "Mailgun Setup Instructions" for step-by-step configuration of inbound email ingestion for both environments.
