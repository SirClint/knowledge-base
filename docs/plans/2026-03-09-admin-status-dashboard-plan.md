# Admin Status Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a host-side `status.sh` script that prints a side-by-side status report for prod and test environments, showing version, AI status, doc/user/queue counts, and last backup info.

**Architecture:** Three parts: (1) a new public `GET /health/summary` API endpoint that returns aggregate stats + version, (2) `APP_VERSION` env var injection at startup/deploy time so each environment reports the git hash it was built from, and (3) `status.sh` bash script that queries both environments and prints a formatted table.

**Tech Stack:** FastAPI (Python), SQLAlchemy async, Bash, curl, git

---

## Task 1: Add `app_version` to config and `GET /health/summary` endpoint

**Files:**
- Modify: `api/config.py`
- Modify: `api/main.py`
- Modify: `.env.example`
- Create: `api/tests/test_summary.py`

**Step 1: Write failing tests**

Create `api/tests/test_summary.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_summary_returns_expected_fields(client):
    r = await client.get("/health/summary")
    assert r.status_code == 200
    data = r.json()
    assert "app_version" in data
    assert "doc_count" in data
    assert "user_count" in data
    assert "review_queue_count" in data
    assert "ai" in data
    assert data["ai"] in ("online", "offline")


async def test_summary_counts_are_integers(client):
    r = await client.get("/health/summary")
    data = r.json()
    assert isinstance(data["doc_count"], int)
    assert isinstance(data["user_count"], int)
    assert isinstance(data["review_queue_count"], int)


async def test_summary_counts_reflect_data(client):
    # Register a user and create a doc — counts should increase
    await client.post("/auth/register", json={"email": "u@test.com", "password": "pass", "role": "editor"})
    login = await client.post("/auth/jwt/login", data={"username": "u@test.com", "password": "pass"})
    token = login.json()["access_token"]
    await client.post("/docs",
        json={"title": "T", "path": "personal/t.md", "body": "b", "tags": []},
        headers={"Authorization": f"Bearer {token}"}
    )
    r = await client.get("/health/summary")
    data = r.json()
    assert data["doc_count"] >= 1
    assert data["user_count"] >= 1


async def test_summary_no_auth_required(client):
    """Summary endpoint must be public — no Authorization header."""
    r = await client.get("/health/summary")
    assert r.status_code == 200


async def test_summary_app_version_from_env(client):
    import os
    from unittest.mock import patch
    with patch("config.settings.app_version", "abc1234"):
        r = await client.get("/health/summary")
    assert r.json()["app_version"] == "abc1234"
```

**Step 2: Run to verify they fail**

```bash
docker compose exec api pytest tests/test_summary.py -v
```
Expected: FAIL — `/health/summary` returns 404

**Step 3: Add `app_version` to `config.py`**

Add one field to `Settings`:

```python
app_version: str = "unknown"
```

**Step 4: Add `GET /health/summary` to `main.py`**

Add after the existing `/health/ai` endpoint:

```python
@app.get("/health/summary")
async def health_summary():
    import httpx
    from sqlalchemy import select, func
    from db.models import Document
    from auth.users import User
    from db.database import async_session_maker

    # AI status
    ai_status = "offline"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            if r.status_code == 200:
                ai_status = "online"
    except Exception:
        pass

    # DB counts
    async with async_session_maker() as session:
        doc_count = (await session.execute(select(func.count()).select_from(Document))).scalar() or 0
        user_count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        review_count = (await session.execute(
            select(func.count()).select_from(Document).where(
                Document.status.in_(["needs_review", "overdue"])
            )
        )).scalar() or 0

    return {
        "app_version": settings.app_version,
        "doc_count": doc_count,
        "user_count": user_count,
        "review_queue_count": review_count,
        "ai": ai_status,
    }
```

**Step 5: Add `INGEST_EMAIL_WHITELIST` and `APP_VERSION` to `.env.example`**

Read `.env.example` first. Append:
```
APP_VERSION=unknown
```

**Step 6: Rebuild and run tests**

```bash
docker compose build api && docker compose up -d api
docker compose exec api pytest tests/test_summary.py -v
```
Expected: all 5 tests PASS

**Step 7: Run full suite**

```bash
docker compose exec api pytest -v
```
Expected: all 51 existing + 5 new = 56 passed

**Step 8: Commit**

```bash
git add api/config.py api/main.py api/tests/test_summary.py .env.example
git commit -m "feat: GET /health/summary endpoint — public aggregate stats and app version"
```

---

## Task 2: Inject APP_VERSION into compose files and scripts

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.test.yml`
- Modify: `start.sh`
- Modify: `deploy.sh`
- Modify: `deploy-test.sh`

**Step 1: Add `APP_VERSION` environment passthrough to `docker-compose.yml`**

Read `docker-compose.yml`. In the `api` service, add an `environment` block:

```yaml
  api:
    build: ./api
    volumes:
      - ./vault:/vault
      - kb_data:/data
    env_file: .env
    environment:
      - APP_VERSION
    depends_on:
      - chromadb
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

**Step 2: Add same to `docker-compose.test.yml`**

Read `docker-compose.test.yml`. Add the same `environment` block to its `api` service:

```yaml
    environment:
      - APP_VERSION
```

**Step 3: Export APP_VERSION in `start.sh`**

Read `start.sh`. Add this line immediately before the `docker compose -f "$COMPOSE_FILE" up -d` line:

```bash
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
```

**Step 4: Export APP_VERSION in `deploy.sh`**

Read `deploy.sh`. Add this line immediately before `docker compose build api ui`:

```bash
export APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
```

**Step 5: Export APP_VERSION in `deploy-test.sh`**

Read `deploy-test.sh`. Add the same line immediately before `docker compose -f docker-compose.test.yml build api ui`.

**Step 6: Verify manually**

Restart prod with the updated start script:
```bash
./start.sh
```

Then check the version is injected:
```bash
curl -s http://localhost:8080/kms/api/health/summary | python3 -m json.tool
```
Expected: `app_version` shows a 7-character git hash, not `"unknown"`

**Step 7: Commit**

```bash
git add docker-compose.yml docker-compose.test.yml start.sh deploy.sh deploy-test.sh
git commit -m "feat: inject APP_VERSION git hash into API containers at startup"
```

---

## Task 3: Write `status.sh`

**Files:**
- Create: `status.sh`

**Step 1: Create `status.sh`**

```bash
#!/usr/bin/env bash
# KMS Admin Status — shows side-by-side prod/test environment status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROD_URL="http://localhost:8080/kms/api"
TEST_URL="http://localhost:8081/kms/api"

# ── Fetch summary from an environment ─────────────────────────────────────────
fetch_summary() {
  local url="$1"
  curl -sf --max-time 3 "${url}/health/summary" 2>/dev/null
}

# ── Parse a JSON field ────────────────────────────────────────────────────────
json_field() {
  echo "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$2',''))" 2>/dev/null
}

# ── Human-readable time since a file was modified ─────────────────────────────
time_ago() {
  local file="$1"
  if [[ ! -f "$file" ]]; then echo "never"; return; fi
  local now
  now=$(date +%s)
  local mod
  mod=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null)
  local diff=$(( now - mod ))
  if   (( diff < 3600 ));   then echo "$(( diff / 60 )) minutes ago"
  elif (( diff < 86400 ));  then echo "$(( diff / 3600 )) hours ago"
  else                           echo "$(( diff / 86400 )) days ago"
  fi
}

# ── Commits behind HEAD ───────────────────────────────────────────────────────
commits_behind() {
  local version="$1"
  local head
  head=$(git rev-parse --short HEAD 2>/dev/null)
  if [[ -z "$version" || "$version" == "unknown" ]]; then echo "?"; return; fi
  if [[ "$version" == "$head" ]]; then echo "0"; return; fi
  # Check if version is in our git history
  if ! git rev-parse "${version}" > /dev/null 2>&1; then echo "?"; return; fi
  git rev-list "${version}..HEAD" --count 2>/dev/null || echo "?"
}

# ── Fetch both environments ───────────────────────────────────────────────────
PROD_JSON=$(fetch_summary "$PROD_URL")
TEST_JSON=$(fetch_summary "$TEST_URL")

# Prod fields
if [[ -n "$PROD_JSON" ]]; then
  PROD_STATUS="● RUNNING"
  PROD_VERSION=$(json_field "$PROD_JSON" "app_version")
  PROD_AI=$(json_field "$PROD_JSON" "ai")
  PROD_DOCS=$(json_field "$PROD_JSON" "doc_count")
  PROD_USERS=$(json_field "$PROD_JSON" "user_count")
  PROD_QUEUE=$(json_field "$PROD_JSON" "review_queue_count")
  PROD_BEHIND=$(commits_behind "$PROD_VERSION")
  if [[ "$PROD_BEHIND" == "0" ]]; then
    PROD_VER_LABEL="v${PROD_VERSION} ✓ current"
  elif [[ "$PROD_BEHIND" == "?" ]]; then
    PROD_VER_LABEL="v${PROD_VERSION} ? unknown"
  else
    PROD_VER_LABEL="v${PROD_VERSION} ⚠ ${PROD_BEHIND} behind"
  fi
else
  PROD_STATUS="○ STOPPED"
  PROD_VER_LABEL="—"
  PROD_AI="—"
  PROD_DOCS="—"
  PROD_USERS="—"
  PROD_QUEUE="—"
fi

# Test fields
if [[ -n "$TEST_JSON" ]]; then
  TEST_STATUS="● RUNNING"
  TEST_VERSION=$(json_field "$TEST_JSON" "app_version")
  TEST_AI=$(json_field "$TEST_JSON" "ai")
  TEST_DOCS=$(json_field "$TEST_JSON" "doc_count")
  TEST_USERS=$(json_field "$TEST_JSON" "user_count")
  TEST_QUEUE=$(json_field "$TEST_JSON" "review_queue_count")
  TEST_BEHIND=$(commits_behind "$TEST_VERSION")
  if [[ "$TEST_BEHIND" == "0" ]]; then
    TEST_VER_LABEL="v${TEST_VERSION} ✓ current"
  elif [[ "$TEST_BEHIND" == "?" ]]; then
    TEST_VER_LABEL="v${TEST_VERSION} ? unknown"
  else
    TEST_VER_LABEL="v${TEST_VERSION} ⚠ ${TEST_BEHIND} behind"
  fi
else
  TEST_STATUS="○ STOPPED"
  TEST_VER_LABEL="—"
  TEST_AI="—"
  TEST_DOCS="—"
  TEST_USERS="—"
  TEST_QUEUE="—"
fi

# ── Backup info ───────────────────────────────────────────────────────────────
LAST_PROD_BACKUP=$(ls -t "${SCRIPT_DIR}/backups"/*-prod.tar.gz 2>/dev/null | head -1)
LAST_TEST_BACKUP=$(ls -t "${SCRIPT_DIR}/backups"/*-test.tar.gz 2>/dev/null | head -1)
PROD_BACKUP_LABEL="${LAST_PROD_BACKUP:+$(basename "$LAST_PROD_BACKUP") ($(time_ago "$LAST_PROD_BACKUP"))}"
TEST_BACKUP_LABEL="${LAST_TEST_BACKUP:+$(basename "$LAST_TEST_BACKUP") ($(time_ago "$LAST_TEST_BACKUP"))}"
PROD_BACKUP_LABEL="${PROD_BACKUP_LABEL:-never}"
TEST_BACKUP_LABEL="${TEST_BACKUP_LABEL:-never}"
BACKUP_COUNT=$(ls "${SCRIPT_DIR}/backups"/*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
BACKUP_SIZE=$(du -sh "${SCRIPT_DIR}/backups"/*.tar.gz 2>/dev/null | awk '{sum+=$1} END{print sum"K"}' || echo "0K")

# ── Git info ──────────────────────────────────────────────────────────────────
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
GIT_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GIT_MSG=$(git log -1 --pretty="%s" 2>/dev/null || echo "")
GIT_DATE=$(git log -1 --pretty="%ad" --date=short 2>/dev/null || echo "")

# ── Print ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                   KMS Admin Status                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
printf "  %-18s %-26s %s\n" "" "PROD (8080)" "TEST (8081)"
printf "  %-18s %-26s %s\n" "Status" "$PROD_STATUS" "$TEST_STATUS"
printf "  %-18s %-26s %s\n" "Version" "$PROD_VER_LABEL" "$TEST_VER_LABEL"
printf "  %-18s %-26s %s\n" "AI" "$PROD_AI" "$TEST_AI"
printf "  %-18s %-26s %s\n" "Documents" "$PROD_DOCS" "$TEST_DOCS"
printf "  %-18s %-26s %s\n" "Users" "$PROD_USERS" "$TEST_USERS"
printf "  %-18s %-26s %s\n" "Review Queue" "$PROD_QUEUE pending" "$TEST_QUEUE pending"
echo ""
printf "  %-18s %s\n" "Last Backup"    "prod: $PROD_BACKUP_LABEL"
printf "  %-18s %s\n" ""               "test: $TEST_BACKUP_LABEL"
printf "  %-18s %s\n" "Backups"        "${BACKUP_COUNT} archives"
echo ""
printf "  %-18s %s\n" "Git Branch"     "$GIT_BRANCH"
printf "  %-18s %s  %s  (%s)\n" "Git HEAD" "$GIT_HEAD" "$GIT_MSG" "$GIT_DATE"
echo ""
```

**Step 2: Make executable**

```bash
chmod +x status.sh
```

**Step 3: Test it manually**

```bash
./status.sh
```

Verify:
- Prod shows `● RUNNING` with a version hash
- Test shows `○ STOPPED` (or `● RUNNING` if started)
- Review queue shows a number
- Last backup shows the timestamp from `backups/`
- Git info shows current branch and HEAD

**Step 4: Test with test environment running**

```bash
./start.sh --test
./status.sh
```

Verify both columns now show `● RUNNING` with potentially different version hashes if test was started at a different commit.

**Step 5: Commit**

```bash
git add status.sh
git commit -m "feat: status.sh — admin status dashboard showing prod/test env health side by side"
```

---

## Final Verification

```bash
# Backend tests
docker compose exec api pytest -v
# Expected: 56 passed

# Manual smoke test
./status.sh
# Expected: formatted table with both environments, version info, counts, backup info
```
