# Account Preservation + Admin CLI Design

## Goal

Ensure user accounts survive deploys. Provide a CLI to create the initial admin account after a fresh install or volume wipe.

## Architecture

Three components:

1. **`api/manage.py`** — standalone management script run inside the API container
2. **Makefile targets** — thin wrappers for developer convenience
3. **Deploy script integration** — automatic export before rebuild, import after restart in both `deploy.sh` and `deploy-test.sh`

---

## `api/manage.py`

Standalone script using `argparse` + `asyncio.run()`. Imports the existing `User` model and `async_session_maker` directly — no FastAPI app startup needed.

### Commands

#### `create-admin`

```
docker compose -f docker-compose.test.yml --env-file .env.test \
  exec api python manage.py create-admin --email X --password Y
```

- Creates a user directly in the DB with `role=admin`, `is_active=True`, `is_superuser=False`, `is_verified=False`
- Uses `PasswordHelper` from `fastapi_users.password` to hash the password (same hasher the app uses)
- If the email already exists: print a clear message and exit 0 (idempotent)
- Does NOT go through the registration endpoint — bypasses `on_after_register` role lock

#### `export-users`

```
docker compose exec api python manage.py export-users --output /data/users.json
```

- Dumps all rows from the `users` table to JSON
- Fields exported: `id`, `email`, `hashed_password`, `role`, `is_active`, `is_superuser`, `is_verified`
- Passwords are always bcrypt hashes — never plaintext
- If no users exist: writes `[]` and exits 0 (harmless on first deploy)
- Output path defaults to `/data/users.json`

#### `import-users`

```
docker compose exec api python manage.py import-users --input /data/users.json
```

- Reads the JSON file, inserts any user whose email does not already exist in the DB
- Skips existing users (no overwrite) — conflict window between export and import is ~30 seconds max
- Preserves `id` (UUID) from export so foreign key references stay consistent
- Prints a summary: `Imported N users, skipped M existing`
- If the file does not exist: prints a warning and exits 0 (safe on very first deploy)

---

## Makefile Targets

All targets operate on the test environment (consistent with every other `make` target):

```makefile
create-admin:
	$(TEST_COMPOSE) exec api python manage.py create-admin --email $(email) --password $(password)

export-users:
	$(TEST_COMPOSE) exec api python manage.py export-users --output /data/users.json

import-users:
	$(TEST_COMPOSE) exec api python manage.py import-users --input /data/users.json
```

Usage:
```bash
make create-admin email=you@example.com password=secret
make export-users
make import-users
```

---

## Deploy Script Integration

### `deploy.sh` (production)

New steps added between existing steps 2 and 3, and after step 4:

```
Step 1: Backup (existing)
Step 2: Human confirmation (existing)
Step 2.5 [NEW]: Export users → /data/users.json
Step 3: Pull latest code (existing)
Step 4: Rebuild and restart (existing)
Step 4.5 [NEW]: Wait for API health, then import users
```

Export command (prod):
```bash
docker compose --env-file .env exec api python manage.py export-users --output /data/users.json
```

Health wait + import (prod):
```bash
echo "Waiting for API to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8080/kms/api/health > /dev/null 2>&1; then break; fi
  sleep 2
done
docker compose --env-file .env exec api python manage.py import-users --input /data/users.json
```

### `deploy-test.sh`

Identical pattern using the test compose file and port 8081.

The export file lives at `/data/users.json` inside the `kb_data` / `kb_data_test` volume — it persists across image rebuilds because volumes are not touched during a normal deploy.

---

## `docs/DEPLOYMENT.md` — New Section

Add an "Account Management" section covering:

- How to create the first admin after fresh install or volume wipe
- What the automatic export/import does and when it runs
- Manual export/import instructions for recovery scenarios

---

## What This Does NOT Cover

- Alembic migrations (full migration system is a separate, larger effort)
- Password reset via CLI (out of scope — admin can reset via the Users page)
- Exporting/importing documents or vault files (covered by `backup.sh`)
