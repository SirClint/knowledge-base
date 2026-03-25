# Account Preservation + Admin CLI Design

## Goal

Ensure user accounts survive image rebuilds during normal deploys. Provide a CLI to create the initial admin account after a fresh install or volume wipe.

> **Scope:** This feature protects accounts across `deploy.sh` / `deploy-test.sh` runs (image rebuilds without volume removal). It does NOT protect against Docker volume wipes — use `backup.sh` for full disaster recovery.

## Architecture

Three components:

1. **`api/manage.py`** — standalone management script run inside the API container
2. **Makefile targets** — thin wrappers for developer convenience
3. **Deploy script integration** — automatic export before rebuild, import after restart in both `deploy.sh` and `deploy-test.sh`

---

## `api/manage.py`

Standalone script using `argparse` + `asyncio.run()`. Imports the existing `User` model and `async_session_maker` directly — no FastAPI app startup needed. Relies on `config.settings.database_url` (set via env in the container) so it always writes to the same database the app uses.

### Commands

#### `create-admin`

```bash
docker compose -f docker-compose.test.yml --env-file .env.test \
  exec api python manage.py create-admin --email X --password Y
```

Both `--email` and `--password` are required `argparse` arguments. Missing either produces an argparse usage error.

- Creates a user directly in the DB with `role=admin`, `is_active=True`, `is_superuser=False`, `is_verified=False`
- Uses `PasswordHelper` from `fastapi_users.password` to hash the password (same hasher the app uses at login)
- If the email already exists: print `User already exists: <email>` and exit 0 (idempotent — safe to run twice)
- Does NOT go through the registration endpoint — bypasses `on_after_register` which (once security hardening is merged) forces all registrations to `role=reader`

#### `export-users`

```bash
docker compose -f docker-compose.test.yml --env-file .env.test \
  exec api python manage.py export-users --output /data/manage/users.json
```

- Dumps all rows from the `users` table to a JSON array
- Fields exported: `id`, `email`, `hashed_password`, `role`, `is_active`, `is_superuser`, `is_verified`
- Passwords are always bcrypt hashes — never plaintext
- If no users exist: writes `[]` and exits 0 (harmless on first deploy)
- `--output` defaults to `/data/manage/users.json`

The file lives inside the `kb_data` / `kb_data_test` Docker volume at `/data/manage/users.json`. This subdirectory keeps the export file clearly separated from ChromaDB's `/data/chroma/` subtree and away from the volume root. Volumes are not removed during a normal deploy (only image layers are rebuilt), so the file persists across the rebuild.

#### `import-users`

```bash
docker compose -f docker-compose.test.yml --env-file .env.test \
  exec api python manage.py import-users --input /data/manage/users.json
```

- Reads the JSON file, inserts any user whose email does not already exist in the DB
- **Skip-on-conflict is intentional:** the live DB is the source of truth. Any user who registered or was modified after the export (during the ~30-second deploy window) already exists in the DB and is left unchanged. The export is only a fallback for records that would otherwise be lost if the image rebuild wiped state (it does not, but this is the safety net).
- Preserves `id` (UUID) from export — UUIDs are stored as VARCHAR in SQLite, safe to insert directly
- Prints a summary: `Imported N users, skipped M existing`
- If the file does not exist: prints a warning and exits 0 (safe on very first deploy with no prior export)
- `--input` defaults to `/data/manage/users.json`

---

## Makefile Targets

All targets operate on the test environment (consistent with every other `make` target).

`--email` and `--password` are required. Running `make create-admin` without them passes empty strings to argparse, which produces a confusing error — always supply both:

```bash
make create-admin email=you@example.com password=secret   # both required
make export-users
make import-users
```

Makefile additions:

```makefile
create-admin:
	$(TEST_COMPOSE) exec api python manage.py create-admin --email $(email) --password $(password)

export-users:
	$(TEST_COMPOSE) exec api python manage.py export-users --output /data/manage/users.json

import-users:
	$(TEST_COMPOSE) exec api python manage.py import-users --input /data/manage/users.json
```

---

## Deploy Script Integration

### `deploy.sh` (production)

New steps inserted between existing steps 2–3 and after step 4. Updated step numbering:

```
Step 1: Backup (existing)
Step 2: Human confirmation (existing)
Step 3 [NEW]: Export users to /data/manage/users.json
Step 4: Pull latest code from main (existing — was step 3)
Step 5: Rebuild and restart (existing — was step 4)
Step 6 [NEW]: Wait for API health, then import users
```

**Step 3 — Export (prod):**
```bash
echo "Step 3/6: Exporting user accounts..."
docker compose --env-file .env exec api python manage.py export-users --output /data/manage/users.json
```

**Step 6 — Health wait + Import (prod):**
```bash
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
  echo "Run manually: docker compose --env-file .env exec api python manage.py import-users"
  exit 1
fi
docker compose --env-file .env exec api python manage.py import-users --input /data/manage/users.json
```

If the API never becomes healthy the script exits non-zero (triggering `set -e`) and prints recovery instructions. It does NOT attempt import against an unready container.

### `deploy-test.sh` (test)

Same pattern with the test compose file and port 8081:

**Step 3 — Export (test):**
```bash
echo "Step 3/6: Exporting user accounts..."
docker compose -f docker-compose.test.yml --env-file .env.test exec api python manage.py export-users --output /data/manage/users.json
```

**Step 6 — Health wait + Import (test):**
```bash
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
  echo "Run manually: docker compose -f docker-compose.test.yml --env-file .env.test exec api python manage.py import-users"
  exit 1
fi
docker compose -f docker-compose.test.yml --env-file .env.test exec api python manage.py import-users --input /data/manage/users.json
```

---

## `docs/DEPLOYMENT.md` — New Section

Add an "Account Management" section after "Backups" covering:

1. **Initial admin setup** — how to create the first admin account after a fresh install or volume wipe using `make create-admin`
2. **Automatic account preservation** — what the export/import in the deploy scripts does and when it runs
3. **Manual recovery** — how to run `make export-users` / `make import-users` by hand
4. **Scope note** — this does not protect against volume wipes; use `backup.sh` + restore procedure for that

---

## What This Does NOT Cover

- Alembic migrations (full migration system is a separate, larger effort)
- Password reset via CLI (admin can reset via the Users page in the UI)
- Exporting/importing documents or vault files (covered by `backup.sh`)
- Docker volume wipes — if `kb_data` is removed, accounts are gone; restore from a `backup.sh` archive
