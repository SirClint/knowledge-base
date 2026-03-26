# Account Preservation + Admin CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `manage.py` CLI script for creating admin accounts and exporting/importing users, and wire automatic export/import into both deploy scripts so accounts survive image rebuilds.

**Architecture:** A standalone `api/manage.py` script imports the existing `User` model and `async_session_maker` directly (no FastAPI app startup). Three subcommands: `create-admin`, `export-users`, `import-users`. Makefile targets wrap the test-env docker exec calls. Both deploy scripts gain an export step before rebuild and a health-wait + import step after restart.

**Tech Stack:** Python asyncio, SQLAlchemy async, fastapi-users PasswordHelper, argparse, bash

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `api/manage.py` | Create | CLI entry point + three async command functions |
| `api/tests/test_manage.py` | Create | Unit tests for all three command functions |
| `Makefile` | Modify | Add `create-admin`, `export-users`, `import-users` targets |
| `deploy.sh` | Modify | Add export (new step 3) and import (new step 6) |
| `deploy-test.sh` | Modify | Same as deploy.sh using test compose file and port 8081 |
| `docs/DEPLOYMENT.md` | Modify | Add Account Management section |

---

### Task 1: `api/manage.py` — management CLI

**Files:**
- Create: `api/manage.py`
- Create: `api/tests/test_manage.py`

#### Background for implementer

The project uses FastAPI + SQLAlchemy async + SQLite. User accounts are managed by `fastapi-users`. The `User` model is in `api/auth/users.py`. The DB session factory is `async_session_maker()` in `api/db/database.py`. `create_db()` in that same file runs `Base.metadata.create_all` — it must be called before any DB operations.

Tests live in `api/tests/`. The `conftest.py` sets environment variables including `DATABASE_URL` pointing to a temp SQLite file. Each test gets a clean DB via the `reset_db` autouse fixture (which sets `_db._engine = None` before each test). Tests are async; `asyncio_mode = auto` is set in `pytest.ini` or `pyproject.toml` — no `@pytest.mark.asyncio` decorator needed.

To run tests: `docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest api/tests/test_manage.py -v`
Or via make: `make pytest` (runs all tests).

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_manage.py`:

```python
import json
import tempfile
import pytest
from pathlib import Path


async def test_create_admin_creates_user_with_admin_role():
    import auth.users  # noqa: F401 — registers User with Base.metadata
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("admin@example.com", "password123")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "admin@example.com"))
        user = result.scalar_one_or_none()

    assert user is not None
    assert user.role == "admin"
    assert user.is_active is True
    assert user.is_superuser is False


async def test_create_admin_is_idempotent():
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    await manage.cmd_create_admin("admin@example.com", "password123")
    # Second call must not raise
    await manage.cmd_create_admin("admin@example.com", "password123")


async def test_create_admin_password_is_hashed():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("admin@example.com", "password123")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "admin@example.com"))
        user = result.scalar_one_or_none()

    assert user.hashed_password != "password123"
    assert user.hashed_password.startswith("$2")  # bcrypt prefix


async def test_export_users_writes_json(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    await manage.cmd_create_admin("admin@example.com", "secret")
    output = str(tmp_path / "users.json")
    await manage.cmd_export_users(output)

    data = json.loads(Path(output).read_text())
    assert len(data) == 1
    assert data[0]["email"] == "admin@example.com"
    assert data[0]["role"] == "admin"
    assert "hashed_password" in data[0]
    assert data[0]["hashed_password"] != "secret"  # must be hashed


async def test_export_users_empty_db_writes_empty_list(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    output = str(tmp_path / "users.json")
    await manage.cmd_export_users(output)

    data = json.loads(Path(output).read_text())
    assert data == []


async def test_import_users_restores_accounts(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    # Seed one user, export, then import into clean session
    await manage.cmd_create_admin("admin@example.com", "secret")
    export_file = str(tmp_path / "users.json")
    await manage.cmd_export_users(export_file)

    # Simulate clean DB by querying before import (user already exists — skip case)
    await manage.cmd_import_users(export_file)

    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
    assert len(users) == 1


async def test_import_users_skips_existing(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("admin@example.com", "secret")
    export_file = str(tmp_path / "users.json")
    await manage.cmd_export_users(export_file)

    # Import again — existing user must not be duplicated
    imported, skipped = await manage.cmd_import_users(export_file)
    assert imported == 0
    assert skipped == 1

    async with async_session_maker() as session:
        count = (await session.execute(
            __import__("sqlalchemy").select(__import__("sqlalchemy").func.count()).select_from(User)
        )).scalar()
    assert count == 1


async def test_import_users_missing_file(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    # Must not raise — just warn and return
    result = await manage.cmd_import_users(str(tmp_path / "nonexistent.json"))
    assert result is None or result == (0, 0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest api/tests/test_manage.py -v
```

Expected: `ModuleNotFoundError: No module named 'manage'` or similar import error.

- [ ] **Step 3: Implement `api/manage.py`**

```python
#!/usr/bin/env python3
"""KMS management CLI — run inside the API container.

Usage:
    python manage.py create-admin --email X --password Y
    python manage.py export-users [--output /data/manage/users.json]
    python manage.py import-users [--input /data/manage/users.json]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path


async def cmd_create_admin(email: str, password: str) -> None:
    import auth.users  # noqa: F401 — registers User with Base.metadata
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select
    import uuid

    await create_db()
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"User already exists: {email}")
            return
        ph = PasswordHelper()
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=ph.hash(password),
            role="admin",
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.commit()
    print(f"Admin created: {email}")


async def cmd_export_users(output: str) -> None:
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select

    await create_db()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        data = [
            {
                "id": str(u.id),
                "email": u.email,
                "hashed_password": u.hashed_password,
                "role": u.role,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "is_verified": u.is_verified,
            }
            for u in users
        ]

    output_path.write_text(json.dumps(data, indent=2))
    print(f"Exported {len(data)} users to {output}")


async def cmd_import_users(input_path: str):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import uuid as uuid_mod

    path = Path(input_path)
    if not path.exists():
        print(f"Warning: {input_path} not found. Skipping import.")
        return None

    await create_db()
    data = json.loads(path.read_text())

    imported = 0
    skipped = 0
    async with async_session_maker() as session:
        for u in data:
            result = await session.execute(select(User).where(User.email == u["email"]))
            if result.scalar_one_or_none():
                skipped += 1
                continue
            user = User(
                id=uuid_mod.UUID(u["id"]),
                email=u["email"],
                hashed_password=u["hashed_password"],
                role=u["role"],
                is_active=u["is_active"],
                is_superuser=u["is_superuser"],
                is_verified=u["is_verified"],
            )
            session.add(user)
            imported += 1
        await session.commit()

    print(f"Imported {imported} users, skipped {skipped} existing")
    return imported, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="KMS management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="Create an admin user directly in the DB")
    p_admin.add_argument("--email", required=True, help="Admin email address")
    p_admin.add_argument("--password", required=True, help="Admin password (will be hashed)")

    p_export = sub.add_parser("export-users", help="Export all users to JSON")
    p_export.add_argument("--output", default="/data/manage/users.json")

    p_import = sub.add_parser("import-users", help="Import users from JSON (skips existing)")
    p_import.add_argument("--input", default="/data/manage/users.json")

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(cmd_create_admin(args.email, args.password))
    elif args.command == "export-users":
        asyncio.run(cmd_export_users(args.output))
    elif args.command == "import-users":
        asyncio.run(cmd_import_users(args.input))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Fix the import test — it needs a fresh DB to demonstrate import**

The `test_import_users_skips_existing` test above verifies the skip path correctly. But there's no test for the happy path where import actually inserts a new user. Add one more test to `test_manage.py` after the existing ones:

```python
async def test_import_users_inserts_new_users(tmp_path):
    """Export from one DB state, clear users manually, re-import — verifies insert path."""
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select, delete
    import manage

    await create_db()
    await manage.cmd_create_admin("admin@example.com", "secret")
    export_file = str(tmp_path / "users.json")
    await manage.cmd_export_users(export_file)

    # Delete all users to simulate a wiped DB
    async with async_session_maker() as session:
        await session.execute(delete(User))
        await session.commit()

    imported, skipped = await manage.cmd_import_users(export_file)
    assert imported == 1
    assert skipped == 0

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "admin@example.com"))
        user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == "admin"
```

- [ ] **Step 5: Run tests — all must pass**

> **Note:** Step 4 above adds the 8th test (`test_import_users_inserts_new_users`). You must complete both Step 1 and Step 4 before running this step — otherwise only 7 tests exist and the count will be off.

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest api/tests/test_manage.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 6: Run full test suite — no regressions**

```bash
make pytest
```

Expected: same pass count as before (currently 113 pass).

- [ ] **Step 7: Commit**

```bash
git add api/manage.py api/tests/test_manage.py
git commit -m "feat: add manage.py CLI for create-admin, export-users, import-users"
```

---

### Task 2: Makefile targets

**Files:**
- Modify: `Makefile` (add after the `logs-api` target, before the `prod-%` guard)

#### Background for implementer

The Makefile uses `TEST_COMPOSE = docker compose -f docker-compose.test.yml --env-file .env.test`. All existing targets use `$(TEST_COMPOSE)`. Add three new targets following the same pattern.

`create-admin` requires `email=` and `password=` passed as make variables. If omitted, Make expands them to empty strings and argparse will error — this is acceptable and documented in DEPLOYMENT.md.

No tests needed for Makefile targets — the underlying `manage.py` functions are already tested.

- [ ] **Step 1: Add targets to Makefile**

Open `Makefile`. After the `logs-api` target and before the `# ── Production guard` comment block, add:

```makefile
create-admin:
	$(TEST_COMPOSE) exec api python manage.py create-admin --email $(email) --password $(password)

export-users:
	$(TEST_COMPOSE) exec api python manage.py export-users --output /data/manage/users.json

import-users:
	$(TEST_COMPOSE) exec api python manage.py import-users --input /data/manage/users.json
```

Also update the `.PHONY` line at the top of the Makefile to include the new targets:

```makefile
.PHONY: build build-ui build-api rebuild up down pytest e2e logs-api create-admin export-users import-users
```

- [ ] **Step 2: Verify targets work**

```bash
make build-api
make create-admin email=test-admin@example.com password=TestPassword123
```

Expected output: `Admin created: test-admin@example.com`

Run again to verify idempotency:
```bash
make create-admin email=test-admin@example.com password=TestPassword123
```

Expected: `User already exists: test-admin@example.com`

```bash
make export-users
```

Expected: `Exported N users to /data/manage/users.json`

```bash
make import-users
```

Expected: `Imported 0 users, skipped N existing`

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: add create-admin, export-users, import-users Makefile targets"
```

---

### Task 3: `deploy.sh` integration

**Files:**
- Modify: `deploy.sh`

#### Background for implementer

Current `deploy.sh` has 4 steps. We're adding 2 new steps, renumbering to 6 total:

- Step 1: Backup (unchanged)
- Step 2: Human confirmation (unchanged)
- **Step 3 (new):** Export users
- Step 4: Pull latest code from main (was step 3)
- Step 5: Rebuild and restart (was step 4)
- **Step 6 (new):** Wait for API health, then import users

The export uses `docker compose --env-file .env exec api ...` (no `-f` flag needed — defaults to `docker-compose.yml` in the project root). The script uses `set -e` so the health-wait loop must exit non-zero on timeout.

Health check URL from the host: `http://localhost:8080/kms/api/health` — Caddy (port 8080) routes `/kms/api/*` → API container `/health`.

- [ ] **Step 1: Update `deploy.sh`**

Replace the entire content of `deploy.sh` with:

```bash
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
```

- [ ] **Step 2: Verify the script is syntactically valid**

```bash
bash -n deploy.sh
```

Expected: no output (no syntax errors).

- [ ] **Step 3: Commit**

```bash
git add deploy.sh
git commit -m "feat: auto export/import users in deploy.sh to preserve accounts across deploys"
```

---

### Task 4: `deploy-test.sh` integration

**Files:**
- Modify: `deploy-test.sh`

#### Background for implementer

Same pattern as `deploy.sh` but using:
- `-f docker-compose.test.yml --env-file .env.test` on all docker compose commands
- Port `8081` in the health check URL
- Step 3 message says "test stack" instead of "production stack"

- [ ] **Step 1: Update `deploy-test.sh`**

Replace the entire content of `deploy-test.sh` with:

```bash
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
```

- [ ] **Step 2: Verify syntax**

```bash
bash -n deploy-test.sh
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add deploy-test.sh
git commit -m "feat: auto export/import users in deploy-test.sh to preserve accounts across deploys"
```

---

### Task 5: `docs/DEPLOYMENT.md` — Account Management section

**Files:**
- Modify: `docs/DEPLOYMENT.md` (add new section after "Backups", before "Resetting an Environment")

#### Background for implementer

`docs/DEPLOYMENT.md` is the operational reference for this project. Add a new "Account Management" section that covers:
1. Creating the initial admin after a fresh install or volume wipe
2. What the automatic export/import does
3. Manual export/import commands
4. Scope note (does not protect against volume wipes)

No tests needed for documentation.

- [ ] **Step 1: Update the "Deploying to Production" section**

In `docs/DEPLOYMENT.md`, find and replace:

```
Run `./deploy.sh` from the project root. It enforces these four steps — **none can be skipped**:
```

with:

```
Run `./deploy.sh` from the project root. It enforces these six steps — **none can be skipped**:
```

Then update the step list below it. The existing steps 3 and 4 become steps 4 and 5. Add new step 3 (export) before them, and new step 6 (health wait + import) after step 5. The updated step descriptions:

- **Step 1:** Automatic backup (unchanged)
- **Step 2:** Human confirmation (unchanged)
- **Step 3 (new):** Export user accounts to `/data/manage/users.json`
- **Step 4:** Pull latest code from main (was step 3)
- **Step 5:** Rebuild and restart (was step 4) — note: existing text says `docker compose build api ui` and `docker compose up -d`
- **Step 6 (new):** Wait for API health (up to 60 seconds), then import users from export file. Exits with error if API never becomes healthy.

- [ ] **Step 2: Add the Account Management section**

In `docs/DEPLOYMENT.md`, find the line:

```
## Resetting an Environment (Wipe All Data)
```

Insert the following block immediately before it.

> **Important:** The block below contains code fences (` ```bash `) inside a markdown section. Copy only the content between the outer display fences in this plan — do NOT paste the outer ` ``` ` delimiters themselves. Verify the markdown renders correctly after pasting (see Step 3).

```markdown
## Account Management

### Creating the initial admin account

After a fresh install or if the database volume is wiped, no user accounts exist. Since the application locks self-registration to the `reader` role, you must create the first admin account from the command line:

```bash
# Test environment
make create-admin email=your@email.com password=YourPassword

# Production environment (run directly — make targets target test only)
docker compose --env-file .env exec api python manage.py create-admin \
  --email your@email.com --password YourPassword
```

If the account already exists, the command prints `User already exists: <email>` and exits cleanly.

### Automatic account preservation during deploys

Both `deploy.sh` and `deploy-test.sh` automatically preserve user accounts across image rebuilds:

1. **Before rebuild** — exports all user accounts to `/data/manage/users.json` inside the data volume
2. **After restart** — waits for the API to be healthy, then imports any users from the export file that don't already exist in the database

This happens automatically — no manual steps required. The export file survives image rebuilds because it lives inside the `kb_data` Docker volume, which is not removed during a normal deploy.

> **Note:** This does not protect against Docker volume wipes (`docker volume rm`). If a volume is wiped, restore from a `backup.sh` archive — see "Restoring from a backup" above.

### Manual export and import

To export or import users manually (e.g., for a recovery scenario):

```bash
# Test environment
make export-users    # writes to /data/manage/users.json inside the container
make import-users    # reads from /data/manage/users.json, skips existing users

# Production environment
docker compose --env-file .env exec api python manage.py export-users --output /data/manage/users.json
docker compose --env-file .env exec api python manage.py import-users --input /data/manage/users.json
```

```

- [ ] **Step 3: Verify the markdown renders correctly**

Open `docs/DEPLOYMENT.md` and confirm:
- The "Deploying to Production" section now says "six steps" and lists all 6
- The new "Account Management" section appears between "Backups" and "Resetting an Environment"
- Code blocks are properly opened and closed (no runaway fences)
- No broken headings or missing blank lines

- [ ] **Step 4: Commit**

```bash
git add docs/DEPLOYMENT.md
git commit -m "docs: add Account Management section, update deploy.sh to 6 steps in DEPLOYMENT.md"
```

---

## Final Verification

- [ ] **Run the full test suite**

```bash
make pytest
```

Expected: all existing tests pass plus the 8 new `test_manage.py` tests. No regressions.

- [ ] **Smoke test the CLI manually**

```bash
make create-admin email=smoke@test.com password=SmokePw123
make export-users
make import-users
```

Expected output:
```
Admin created: smoke@test.com
Exported N users to /data/manage/users.json
Imported 0 users, skipped N existing
```
