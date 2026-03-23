# Security Hardening Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close critical application-layer and transport security gaps — path traversal, auth role escalation, rate limiting, CORS, audit logging, and TLS config hooks — in a single PR before any public exposure.

**Architecture:** All changes are in the FastAPI API, Caddy reverse proxy config, and Docker build files. No new services required. Rate limiting via `slowapi` middleware. Audit logging via a new SQLite table. TLS via Caddy env-var-driven config.

**Tech Stack:** Python 3.12, FastAPI, fastapi-users 13, SQLAlchemy async, slowapi, Caddy 2, Docker Compose, pytest + httpx ASGITransport.

**Spec:** `docs/superpowers/specs/2026-03-09-security-hardening-design.md`

**How to run tests:** Tests run inside Docker. After editing API code, always rebuild first:
```bash
make build-api        # rebuild API container with new code
make pytest           # run all backend tests inside container
```
To run a specific test file: `docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_foo.py`

**Note on 1.12 (UI inline styles):** The inline-style sweep is a separate PR after this one merges. The CSP header in Caddy ships commented out and is activated in that follow-on PR.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `api/tests/conftest.py` | Modify | Fix SECRET_KEY length; add `create_test_user()` DB helper |
| `api/config.py` | Modify | Add `allowed_origins`, `enable_api_docs`; add `model_validator` for SECRET_KEY |
| `api/docs_/service.py` | Modify | Add `_safe_path()` guard; add `from fastapi import HTTPException` |
| `api/docs_/router.py` | Modify | Apply `_safe_path()` to GET read endpoint |
| `api/auth/users.py` | Modify | Add `on_after_register` role lockdown |
| `api/ingestion/router.py` | Modify | Role gate, token dedup, body size cap |
| `api/db/models.py` | Modify | Add `AuditLog`, `UsedToken` models |
| `api/audit/__init__.py` | Create | Empty — creates `audit` package |
| `api/audit/service.py` | Create | `log_event()` helper |
| `api/admin/router.py` | Modify | Add `GET /admin/audit-log` endpoint |
| `api/main.py` | Modify | CORS, slowapi, disable API docs, auth health endpoints, login-failure middleware |
| `api/requirements.txt` | Modify | Add `slowapi` |
| `api/Dockerfile` | Modify | Remove `--reload` from CMD |
| `docker-compose.test.yml` | Modify | Override CMD to add `--reload` for dev |
| `caddy/Caddyfile` | Modify | Security headers, TLS mode env-var hooks |
| `.env.example` | Modify | SECRET_KEY instruction |
| `.env.test` | Modify | 32-char test key, `ENABLE_API_DOCS=true` |
| `api/tests/test_security.py` | Create | New test file for security-specific cases |
| `api/tests/test_auth.py` | Modify | Update to verify role lockdown |
| `api/tests/test_docs.py` | Modify | Update fixtures to use `create_test_user()` |
| `api/tests/test_admin.py` | Modify | Update fixtures to use `create_test_user()` |
| `api/tests/test_email_ingestion.py` | Modify | Add token dedup + body size tests |
| `api/tests/test_ingestion.py` | Create | Test role gate on POST /ingest |
| `api/limiter.py` | Create | Shared slowapi `Limiter` instance (avoids circular import) |

---

## Task 1: Fix Test Infrastructure

The `conftest.py` sets `SECRET_KEY = "test-secret-key"` (15 chars). Once the `model_validator` is added in Task 2, this will crash every test. Fix it first so all tests remain green.

**Files:**
- Modify: `api/tests/conftest.py`

- [ ] **Step 1: Update SECRET_KEY in conftest and add `create_test_user` helper**

Replace the existing conftest content:

```python
import os
import tempfile
import pytest

# Set test environment BEFORE any app modules are imported
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir}/test.db"
os.environ["VAULT_PATH"] = _tmpdir
os.environ.setdefault("SECRET_KEY", "test-secret-key-placeholder-32ch")  # must be >=32 chars
os.environ["CHROMADB_PATH"] = f"{_tmpdir}/chroma"


@pytest.fixture(autouse=True)
async def reset_db():
    """Reset the lazy DB engine between tests so each test gets a clean state."""
    import db.database as _db
    _db._engine = None
    _db._maker = None
    yield
    if _db._engine:
        await _db._engine.dispose()
    _db._engine = None
    _db._maker = None


async def create_test_user(email: str, password: str, role: str) -> None:
    """Create a user directly in the DB with the specified role.

    Bypasses the /auth/register endpoint (which now forces role=reader via on_after_register).
    Use this in fixtures that need editor or admin access.
    """
    import auth.users  # noqa: F401 — ensures User model is registered with Base
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper

    await create_db()
    ph = PasswordHelper()
    hashed = ph.hash(password)
    async with async_session_maker() as session:
        user = User(
            email=email,
            hashed_password=hashed,
            role=role,
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.commit()
```

- [ ] **Step 2: Build and run all tests — expect green (or same failures as before)**

```bash
make build-api && make pytest
```

Expected: same pass/fail ratio as before this change. If new failures appear, stop and diagnose before continuing.

- [ ] **Step 3: Commit**

```bash
git add api/tests/conftest.py
git commit -m "test: fix SECRET_KEY length in conftest, add create_test_user helper"
```

---

## Task 2: Secret Key Model Validator (spec 1.11)

**Files:**
- Modify: `api/config.py`
- Modify: `.env.example`
- Modify: `.env.test`

- [ ] **Step 1: Write the failing test**

Add to `api/tests/test_security.py` (create new file):

```python
import pytest


async def test_weak_secret_key_raises_on_startup(monkeypatch):
    """Settings should refuse to construct with a short or default SECRET_KEY."""
    import importlib
    import os

    monkeypatch.setenv("SECRET_KEY", "tooshort")
    # Force re-import of config to trigger Settings() construction
    import config
    with pytest.raises((ValueError, RuntimeError)):
        importlib.reload(config)


async def test_changeme_secret_key_raises_on_startup(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "changeme")
    import config, importlib
    with pytest.raises((ValueError, RuntimeError)):
        importlib.reload(config)
```

- [ ] **Step 2: Run to verify tests fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_security.py -k "secret_key"
```

Expected: FAIL (no validator exists yet).

- [ ] **Step 3: Add model_validator to config.py**

```python
from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    secret_key: str = "changeme"
    vault_path: str = "/vault"
    ollama_url: str = "http://ollama:11434"
    database_url: str = "sqlite+aiosqlite:////data/kb.db"
    chromadb_path: str = "/data/chroma"
    mailgun_webhook_signing_key: str = ""
    ingest_email_whitelist: str = ""
    app_version: str = "unknown"
    allowed_origins: str = "http://localhost:8080,http://localhost:8081"
    enable_api_docs: bool = False

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        if self.secret_key in ("changeme", "") or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY is insecure. Generate one with: openssl rand -hex 32"
            )
        return self

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 4: Update .env.example**

Change line 1 to:
```
SECRET_KEY=<generate with: openssl rand -hex 32>
```

- [ ] **Step 5: Update .env.test**

Ensure the first line of `.env.test` is a valid 32-char key:
```
SECRET_KEY=test-secret-key-placeholder-32ch
ENABLE_API_DOCS=true
```
(Keep all other existing lines.)

- [ ] **Step 6: Build and run all tests — all green**

```bash
make build-api && make pytest
```

Expected: All tests pass. The `test_security.py` secret key tests should now pass.

- [ ] **Step 7: Commit**

```bash
git add api/config.py .env.example .env.test api/tests/test_security.py
git commit -m "feat: add SECRET_KEY model_validator, reject insecure keys at startup"
```

---

## Task 3: Path Traversal Guard (spec 1.1)

**Files:**
- Modify: `api/docs_/service.py`
- Modify: `api/docs_/router.py`

- [ ] **Step 1: Write failing tests**

Add to `api/tests/test_security.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def editor_client():
    await create_test_user("editor@test.com", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "editor@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_path_traversal_get_blocked(editor_client):
    """GET with path traversal must return 400, not read a file outside vault."""
    r = await editor_client.get("/docs/../../etc/passwd")
    assert r.status_code == 400


async def test_path_traversal_create_blocked(editor_client):
    """POST with traversal path must return 400."""
    r = await editor_client.post("/docs", json={
        "title": "Evil",
        "path": "../../tmp/evil.md",
        "body": "bad",
        "tags": [],
    })
    assert r.status_code == 400


async def test_path_traversal_update_blocked(editor_client):
    """PUT with traversal path must return 400."""
    r = await editor_client.put("/docs/../../etc/shadow", json={"title": "x"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_security.py -k "traversal"
```

Expected: FAIL — currently returns 404 or 200, not 400.

- [ ] **Step 3: Add `_safe_path` to service.py**

At the top of `api/docs_/service.py`, add the import and helper:

```python
from fastapi import HTTPException  # add this import
```

Add this function before `write_doc_file`:

```python
def _safe_path(path: str) -> Path:
    """Resolve path against vault root and reject any traversal outside it."""
    vault_root = Path(settings.vault_path).resolve()
    resolved = (vault_root / path).resolve()
    # Use is_relative_to (Python 3.9+) to avoid the startswith prefix-bypass bug:
    # e.g. vault=/data/vault would incorrectly allow /data/vault-escape with startswith
    if not resolved.is_relative_to(vault_root):
        raise HTTPException(status_code=400, detail="Invalid path")
    return resolved
```

Call `_safe_path(path)` as the first line of `write_doc_file`, `get_doc`, `update_doc`, and `delete_doc`:

```python
async def write_doc_file(path: str, title: str, body: str, meta: dict):
    _safe_path(path)  # add this line
    full_path = Path(settings.vault_path) / path
    ...

async def get_doc(path: str, session: AsyncSession) -> Document | None:
    _safe_path(path)  # add this line
    result = await session.execute(...)
    ...

async def update_doc(path: str, updates: dict, session: AsyncSession, saved_by: str = "") -> Document | None:
    _safe_path(path)  # add this line
    doc = await get_doc(path, session)
    ...

async def delete_doc(path: str, session: AsyncSession) -> bool:
    _safe_path(path)  # add this line
    doc = await get_doc(path, session)
    ...
```

- [ ] **Step 4: Apply `_safe_path` to the router read endpoint**

In `api/docs_/router.py`, add the import at the top:
```python
from docs_.service import create_doc, get_doc, update_doc, delete_doc, _safe_path
```

In the `read` endpoint, add as the first line before the vault file read:
```python
@router.get("/{path:path}")
async def read(path: str, session=Depends(get_session), user=Depends(current_active_user)):
    _safe_path(path)  # add this line
    doc = await get_doc(path, session)
    ...
```

- [ ] **Step 5: Build and run security tests**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_security.py -k "traversal"
```

Expected: All traversal tests PASS.

- [ ] **Step 6: Run all tests to confirm no regressions**

```bash
make pytest
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add api/docs_/service.py api/docs_/router.py api/tests/test_security.py
git commit -m "feat: add path traversal guard to vault file operations"
```

---

## Task 4: Block Admin Self-Registration + Update Test Fixtures (spec 1.2)

This task changes the behavior of `/auth/register` — it always produces a `reader` regardless of submitted role. Existing test fixtures in `test_docs.py` and `test_admin.py` that create editor/admin users via the registration endpoint must be migrated to use `create_test_user()`.

**Files:**
- Modify: `api/auth/users.py`
- Modify: `api/tests/test_auth.py`
- Modify: `api/tests/test_docs.py`
- Modify: `api/tests/test_admin.py`

- [ ] **Step 1: Write failing test**

Add to `api/tests/test_auth.py`:

```python
async def test_register_as_admin_gets_reader(client):
    """Submitting role=admin at registration must produce a reader."""
    r = await client.post("/auth/register", json={
        "email": "wannabe_admin@example.com",
        "password": "Securepass1!",
        "role": "admin",
    })
    assert r.status_code == 201

    login = await client.post("/auth/jwt/login", data={
        "username": "wannabe_admin@example.com",
        "password": "Securepass1!",
    })
    token = login.json()["access_token"]

    # Try an admin action — must fail with 403
    r = await client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_register_as_editor_gets_reader(client):
    """Submitting role=editor at registration must produce a reader."""
    r = await client.post("/auth/register", json={
        "email": "wannabe_editor@example.com",
        "password": "Securepass1!",
        "role": "editor",
    })
    assert r.status_code == 201

    login = await client.post("/auth/jwt/login", data={
        "username": "wannabe_editor@example.com",
        "password": "Securepass1!",
    })
    token = login.json()["access_token"]

    # Try an editor action — must fail with 403
    r = await client.post("/docs", json={"title": "T", "path": "x.md", "body": "b", "tags": []},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_auth.py -k "gets_reader"
```

Expected: FAIL — currently registration grants the requested role.

- [ ] **Step 3: Add `on_after_register` override to UserManager in users.py**

In `api/auth/users.py`, update the `UserManager` class:

```python
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request=None):
        # Force role to reader regardless of submitted value.
        # user is a detached instance at this point — use self.user_db.update()
        # which acquires the correct session from the DI-managed user_db adapter.
        if user.role != "reader":
            await self.user_db.update(user, {"role": "reader"})
```

- [ ] **Step 4: Run auth tests**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_auth.py
```

Expected: All `test_auth.py` tests pass including the two new ones.

- [ ] **Step 5: Update `test_docs.py` — migrate `editor_client` fixture**

The `editor_client` fixture currently registers via the API (will get `reader` now). Replace it:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    await create_test_user("ed@test.com", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c
```

- [ ] **Step 6: Update `test_admin.py` — migrate admin fixtures similarly**

Read the current `test_admin.py` fixtures and replace any API-registered admin/editor users with `create_test_user()` calls. Pattern:

```python
@pytest.fixture
async def admin_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    await create_test_user("admin@test.com", "Securepass1!", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "admin@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c
```

Apply the same pattern to any other test files that have role-specific fixtures.

- [ ] **Step 7: Run all tests**

```bash
make pytest
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add api/auth/users.py api/tests/test_auth.py api/tests/test_docs.py api/tests/test_admin.py
git commit -m "feat: force role=reader on self-registration, update test fixtures"
```

---

## Task 5: Role Gate POST /ingest (spec 1.3)

**Files:**
- Modify: `api/ingestion/router.py`
- Create: `api/tests/test_ingestion.py` (new file — the existing `test_email_ingestion.py` covers the email endpoint; this new file covers the authenticated `POST /ingest` endpoint)

- [ ] **Step 1: Write failing test**

Create `api/tests/test_ingestion.py`:

```python
async def test_reader_cannot_ingest(client):
    """Readers must receive 403 on POST /ingest."""
    from tests.conftest import create_test_user
    import auth.users  # noqa
    from db.database import create_db
    await create_db()
    await create_test_user("reader@test.com", "Securepass1!", "reader")
    r = await client.post("/auth/jwt/login", data={"username": "reader@test.com", "password": "Securepass1!"})
    token = r.json()["access_token"]
    r = await client.post("/ingest", json={"message": "test"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
```

- [ ] **Step 2: Run to verify it fails**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_ingestion.py -k "reader_cannot"
```

Expected: FAIL — currently returns 200 or 503 (AI unavailable), not 403.

- [ ] **Step 3: Change dependency in ingestion/router.py**

In `api/ingestion/router.py`, line 37:
```python
# Before:
async def ingest(payload: IngestPayload, session=Depends(get_session), user=Depends(current_active_user)):

# After:
async def ingest(payload: IngestPayload, session=Depends(get_session), user=Depends(require_editor)):
```

Also add `require_editor` to the imports from `auth.users`.

- [ ] **Step 4: Run tests**

```bash
make build-api && make pytest
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/ingestion/router.py api/tests/test_ingestion.py
git commit -m "feat: require editor role for POST /ingest"
```

---

---

## Task 6: CORS Policy (spec 1.5)

**Files:**
- Modify: `api/main.py`
- Modify: `api/config.py` (already has `allowed_origins` from Task 2)

- [ ] **Step 1: Write failing test**

Add to `api/tests/test_security.py`:

```python
async def test_cors_allowed_origin(client):
    """Requests from allowed origin include CORS headers."""
    r = await client.options("/health", headers={
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


async def test_cors_disallowed_origin(client):
    """Requests from unknown origin do not get CORS allow header."""
    r = await client.options("/health", headers={
        "Origin": "http://evil.example.com",
        "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") != "http://evil.example.com"
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_security.py -k "cors"
```

Expected: FAIL — no CORS middleware yet.

- [ ] **Step 3: Add CORSMiddleware to main.py**

In `api/main.py`, after the `app = FastAPI(...)` line:

```python
from fastapi.middleware.cors import CORSMiddleware
from config import settings

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
```

- [ ] **Step 4: Run tests**

```bash
make build-api && make pytest
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add api/main.py api/tests/test_security.py
git commit -m "feat: add CORS policy locked to ALLOWED_ORIGINS env var"
```

---

## Task 7: Protect API Docs and Health Endpoints (spec 1.6)

**Files:**
- Modify: `api/main.py`
- Modify: `api/config.py` (already has `enable_api_docs` from Task 2)

- [ ] **Step 1: Write failing tests**

Add to `api/tests/test_security.py`:

```python
async def test_api_docs_enabled_in_test_env(client):
    """In test env (ENABLE_API_DOCS=true), /api-docs should return 200."""
    # This test is a DOCUMENTATION STUB — it always passes and cannot be used
    # as a failing-first TDD test. Skip the "verify fail" step for this test only.
    # Production behavior (docs_url=None) is verified manually:
    #   curl http://localhost:8081/kms/api/api-docs → 200 (test env)
    #   curl http://localhost:8080/kms/api/api-docs → 404 (prod env, ENABLE_API_DOCS not set)
    r = await client.get("/api-docs")
    assert r.status_code == 200


async def test_health_summary_requires_auth(client):
    """GET /health/summary is inaccessible without a JWT."""
    r = await client.get("/health/summary")
    assert r.status_code == 401


async def test_health_ai_requires_auth(client):
    """GET /health/ai is inaccessible without a JWT."""
    r = await client.get("/health/ai")
    assert r.status_code == 401


async def test_health_liveness_is_public(client):
    """GET /health (liveness) remains public."""
    r = await client.get("/health")
    assert r.status_code == 200
```

- [ ] **Step 2: Run to verify health tests fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_security.py -k "health"
```

Expected: `test_health_summary_requires_auth` and `test_health_ai_requires_auth` FAIL (currently return 200). `test_api_docs_enabled_in_test_env` is a documentation stub — it will pass immediately and cannot be used as a failing-first test. That is expected.

- [ ] **Step 3: Update FastAPI app construction in main.py**

```python
# Change the FastAPI() constructor:
app = FastAPI(
    title="Knowledge Base API",
    lifespan=lifespan,
    docs_url="/api-docs" if settings.enable_api_docs else None,
    redoc_url="/api-redoc" if settings.enable_api_docs else None,
)
```

Add `Depends(current_active_user)` to both health endpoints:

```python
from auth.users import current_active_user

@app.get("/health/ai")
async def health_ai(user=Depends(current_active_user)):
    ...

@app.get("/health/summary")
async def health_summary(user=Depends(current_active_user)):
    ...
```

- [ ] **Step 4: Run tests**

```bash
make build-api && make pytest
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add api/main.py api/tests/test_security.py
git commit -m "feat: disable API docs in prod, auth-gate /health/ai and /health/summary"
```

---

## Task 8: Rate Limiting (spec 1.4)

**Files:**
- Modify: `api/requirements.txt`
- Create: `api/limiter.py` (shared limiter instance — avoids circular import)
- Modify: `api/main.py`
- Modify: `api/ingestion/router.py`

- [ ] **Step 1: Add slowapi to requirements.txt**

```
slowapi==0.1.9
```

- [ ] **Step 2: Write test documenting rate limit config**

Add to `api/tests/test_security.py`:

```python
async def test_rate_limit_headers_present_on_login(client):
    """Login endpoint returns X-RateLimit-Limit header from slowapi."""
    r = await client.post("/auth/jwt/login", data={
        "username": "nonexistent@test.com",
        "password": "wrongpass",
    })
    # slowapi adds x-ratelimit-limit on every response from a rate-limited route.
    # This test FAILS before slowapi is wired (no such header) and PASSES after.
    assert "x-ratelimit-limit" in r.headers
```

- [ ] **Step 3: Create api/limiter.py (shared limiter instance)**

`ingestion/router.py` needs the limiter, and `main.py` also imports it. Importing `main` from `ingestion/router.py` would create a circular import (`main → ingestion.router → main`). Solve this by putting the limiter in its own module:

```python
# api/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

- [ ] **Step 4: Wire slowapi into main.py**

Import from `limiter.py` (not defined locally):

```python
from limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
```

fastapi-users routes are registered via `include_router` and can't receive `@limiter.limit` decorators directly. Applying slowapi's private `_check_request_limit` with a `None` endpoint raises `AttributeError` in slowapi 0.1.9. Use a simple self-contained in-memory rate limiter for the auth endpoints instead:

```python
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class _SimpleRateLimiter:
    """Thread-safe in-memory rate limiter for per-IP, per-path limiting."""

    # (method, path) → (max_requests, window_seconds)
    LIMITS: dict[tuple[str, str], tuple[int, int]] = {
        ("POST", "/auth/jwt/login"): (10, 60),
        ("POST", "/auth/register"): (5, 60),
        ("POST", "/ingest/email"): (20, 60),
    }

    def __init__(self):
        self._log: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_req: int, window: int) -> bool:
        now = time.monotonic()
        times = [t for t in self._log[key] if now - t < window]
        self._log[key] = times
        if len(times) >= max_req:
            return False
        self._log[key].append(now)
        return True


_path_limiter = _SimpleRateLimiter()


class PathRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        limit_cfg = _SimpleRateLimiter.LIMITS.get((request.method, request.url.path))
        if limit_cfg:
            ip = request.client.host if request.client else "unknown"
            key = f"{ip}:{request.method}:{request.url.path}"
            if not _path_limiter.is_allowed(key, *limit_cfg):
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)


app.add_middleware(PathRateLimitMiddleware)
```

This avoids all slowapi private APIs. The `/ingest` per-user limit still uses slowapi via the route decorator (which has full public API access).

- [ ] **Step 5: Add per-user rate limit to POST /ingest in ingestion/router.py**

```python
from jose import jwt as jose_jwt, JWTError
from slowapi.util import get_remote_address
from fastapi import Request
from config import settings
from limiter import limiter  # import from limiter.py, NOT from main (avoids circular import)

def _key_by_user(request: Request) -> str:
    """Rate-limit /ingest per authenticated user, falling back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ")
        try:
            payload = jose_jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            return payload.get("sub") or get_remote_address(request)
        except JWTError:
            pass
    return get_remote_address(request)

@router.post("")
@limiter.limit("30/minute", key_func=_key_by_user)
async def ingest(request: Request, payload: IngestPayload, session=Depends(get_session), user=Depends(require_editor)):
    ...
```

**Important:** The `request: Request` parameter must be the first positional parameter for slowapi to work.

- [ ] **Step 6: Build and run tests**

```bash
make build-api && make pytest
```

Expected: All pass. The rate-limit header test passes.

- [ ] **Step 7: Commit**

```bash
git add api/requirements.txt api/limiter.py api/main.py api/ingestion/router.py api/tests/test_security.py
git commit -m "feat: add slowapi rate limiting to auth and ingestion endpoints"
```

---

## Task 9: Email Ingestion Hardening (spec 1.7)

**Files:**
- Modify: `api/db/models.py`
- Modify: `api/ingestion/router.py`

- [ ] **Step 1: Write failing tests**

Add to `api/tests/test_email_ingestion.py`:

```python
import hashlib


async def test_email_token_dedup_rejected(client):
    """Second request with same Mailgun token must be rejected with 403."""
    signing_key = "test-signing-key"
    timestamp = str(int(time.time()))
    token = "unique-token-dedup-test"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    data = {
        "timestamp": timestamp,
        "token": token,
        "signature": signature,
        "sender": "sender@example.com",
        "subject": "Test",
        "body-plain": "content",
    }

    from unittest.mock import patch, AsyncMock
    mock_result = {"action": "create", "path": "personal/test.md", "needs_review": False, "message": "ok"}

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"), \
         patch("ingestion.router.ingest_message", new=AsyncMock(return_value=mock_result)):
        r1 = await client.post("/ingest/email", data=data)
        assert r1.status_code == 200

        r2 = await client.post("/ingest/email", data=data)
        assert r2.status_code == 403


async def test_email_body_size_cap(client):
    """Email body exceeding 50,000 chars is rejected with 413."""
    signing_key = "test-signing-key"
    timestamp = str(int(time.time()))
    token = "size-cap-token-abc"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            "sender": "sender@example.com",
            "subject": "Big",
            "body-plain": "x" * 50_001,
        })
    assert r.status_code == 413
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_email_ingestion.py -k "dedup or size_cap"
```

Expected: FAIL.

- [ ] **Step 3: Add UsedToken model to db/models.py**

```python
class UsedToken(Base):
    __tablename__ = "used_tokens"

    token_hash = Column(String(64), primary_key=True)  # SHA-256 hex, fixed 64 chars
    used_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Update ingestion/router.py**

Add at the top:
```python
import hashlib
from datetime import datetime, timedelta
from db.models import UsedToken
from db.database import async_session_maker
from fastapi import BackgroundTasks
```

Add a prune helper (runs in background after response):
```python
async def _prune_used_tokens():
    """Prune tokens older than 24 hours. Uses its own session."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    async with async_session_maker() as session:
        from sqlalchemy import delete
        await session.execute(delete(UsedToken).where(UsedToken.used_at < cutoff))
        await session.commit()
```

Update the `ingest_email` endpoint:
```python
@router.post("/email")
async def ingest_email(
    request: Request,
    background_tasks: BackgroundTasks,
    session=Depends(get_session),
):
    form = await request.form()
    timestamp = form.get("timestamp", "")
    token = form.get("token", "")
    signature = form.get("signature", "")
    sender = form.get("sender", "")
    subject = form.get("subject", "")
    body_plain = form.get("body-plain", "")

    # Body size cap
    if len(body_plain) > 50_000:
        raise HTTPException(status_code=413, detail="Email body too large")

    # Verify Mailgun signature
    if not _verify_mailgun_signature(settings.mailgun_webhook_signing_key, timestamp, token, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Check sender whitelist
    whitelist = [e.strip().lower() for e in settings.ingest_email_whitelist.split(",") if e.strip()]
    if not whitelist or sender.lower() not in whitelist:
        raise HTTPException(status_code=403, detail="Sender not authorized")

    # Token deduplication
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    existing = await session.get(UsedToken, token_hash)
    if existing:
        raise HTTPException(status_code=403, detail="Duplicate request")
    session.add(UsedToken(token_hash=token_hash))
    await session.commit()

    # Prune old tokens after response
    background_tasks.add_task(_prune_used_tokens)

    # Combine subject + body and pass through existing AI ingestion pipeline
    message = f"{subject}\n\n{body_plain}".strip() if subject else body_plain
    try:
        await ingest_message(message, session)
    except ValueError as e:
        print(f"Email ingestion AI error: {e}")
    return {"status": "queued"}
```

- [ ] **Step 5: Build and run tests**

```bash
make build-api && make pytest
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add api/db/models.py api/ingestion/router.py api/tests/test_email_ingestion.py
git commit -m "feat: add email token deduplication and body size cap"
```

---

## Task 10: Audit Log — Models and Service (spec 1.8 part 1)

**Files:**
- Create: `api/audit/__init__.py`
- Create: `api/audit/service.py`
- Modify: `api/db/models.py`

- [ ] **Step 1: Write failing test**

Create `api/tests/test_audit.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def editor_client():
    import auth.users  # noqa
    from db.database import create_db
    await create_db()
    await create_test_user("ed@audit.test", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "ed@audit.test", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_log_event_writes_to_db(editor_client):
    """log_event() creates an AuditLog row in the database."""
    from db.database import async_session_maker
    from db.models import AuditLog
    from audit.service import log_event
    from sqlalchemy import select

    async with async_session_maker() as session:
        await log_event(session, actor_email="test@test.com", action="test.event", target="some/doc.md")

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "test.event")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.actor_email == "test@test.com"
        assert row.target == "some/doc.md"
```

- [ ] **Step 2: Run to verify it fails**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_audit.py
```

Expected: FAIL — `AuditLog` model and `audit.service` don't exist yet.

- [ ] **Step 3: Add AuditLog model to db/models.py**

```python
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    actor_email = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target = Column(String, nullable=True)
    detail = Column(String, nullable=True)  # freeform JSON string
    ip_address = Column(String, nullable=True)
```

- [ ] **Step 4: Create api/audit/__init__.py (empty)**

```python
```

- [ ] **Step 5: Create api/audit/service.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AuditLog


async def log_event(
    session: AsyncSession,
    actor_email: str,
    action: str,
    target: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """Write a single audit event to the AuditLog table."""
    entry = AuditLog(
        actor_email=actor_email,
        action=action,
        target=target,
        detail=detail,
        ip_address=ip,
    )
    session.add(entry)
    await session.commit()
```

- [ ] **Step 6: Build and run audit tests**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_audit.py
```

Expected: PASS.

- [ ] **Step 7: Run all tests**

```bash
make pytest
```

Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add api/audit/__init__.py api/audit/service.py api/db/models.py api/tests/test_audit.py
git commit -m "feat: add AuditLog model and log_event() helper"
```

---

## Task 11: Audit Log — Wire Event Logging (spec 1.8 part 2)

**Files:**
- Modify: `api/auth/users.py`
- Modify: `api/docs_/router.py`
- Modify: `api/admin/router.py`
- Modify: `api/ingestion/router.py`

- [ ] **Step 1: Write failing tests**

Add to `api/tests/test_audit.py`:

```python
async def test_doc_create_logged(editor_client):
    """Creating a document writes a doc.create audit event."""
    from db.database import async_session_maker
    from db.models import AuditLog
    from sqlalchemy import select

    await editor_client.post("/docs", json={
        "title": "Audit Test Doc",
        "path": "team/audit-test.md",
        "body": "content",
        "tags": [],
    })

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "doc.create")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.target == "team/audit-test.md"


async def test_login_success_logged(client):
    """Successful login writes an auth.login_success audit event."""
    from db.database import async_session_maker, create_db
    from db.models import AuditLog
    from sqlalchemy import select
    from tests.conftest import create_test_user
    import auth.users  # noqa

    await create_db()
    await create_test_user("logintest@test.com", "Securepass1!", "reader")
    await client.post("/auth/jwt/login", data={
        "username": "logintest@test.com",
        "password": "Securepass1!",
    })

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.action == "auth.login_success",
                AuditLog.actor_email == "logintest@test.com",
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_audit.py -k "logged"
```

Expected: FAIL — no event wiring yet.

- [ ] **Step 3: Wire login_success in users.py**

Update `UserManager.on_after_login`:

```python
async def on_after_login(self, user: User, request=None, response=None):
    from db.database import async_session_maker
    from audit.service import log_event
    ip = request.client.host if request and request.client else None
    async with async_session_maker() as session:
        await log_event(session, actor_email=user.email, action="auth.login_success", ip=ip)
```

- [ ] **Step 4: Wire doc events in docs_/router.py**

Add to the `create` endpoint after calling `create_doc`:
```python
from audit.service import log_event

# In create():
    doc = await create_doc(...)
    await log_event(session, actor_email=user.email, action="doc.create",
                    target=payload.path, ip=request.client.host if request.client else None)
```

Add `request: Request` to the endpoint signature if not already present.

Apply the same pattern to `update` (action `"doc.update"`) and `delete` (action `"doc.delete"`).

- [ ] **Step 5: Wire admin events in admin/router.py**

In `change_role`: add `await log_event(session, actor_email=current.email, action="user.role_change", target=str(user_id), detail=body.role)`

In `delete_user`: add `await log_event(session, actor_email=current.email, action="user.delete", target=str(user_id))`

In `reset_password`: add `await log_event(session, actor_email=_admin.email, action="user.password_reset", target=str(user_id))`

Import `log_event` from `audit.service` at the top of `admin/router.py`.

- [ ] **Step 6: Wire ingest.email in ingestion/router.py**

After the `UsedToken` insert and before calling `ingest_message`, add:
```python
import json as _json
from audit.service import log_event as _log_event

await _log_event(
    session,
    actor_email="anonymous",
    action="ingest.email",
    target=sender,
    detail=_json.dumps({"subject": subject[:200]}),  # subject only, never body
)
```

- [ ] **Step 7: Build and run audit tests**

```bash
make build-api && make pytest
```

Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add api/auth/users.py api/docs_/router.py api/admin/router.py api/ingestion/router.py api/tests/test_audit.py
git commit -m "feat: wire audit log events for login, doc CRUD, admin actions, email ingest"
```

---

## Task 12: Login Failure Middleware + Admin Audit Log Endpoint (spec 1.8 part 3)

**Files:**
- Modify: `api/main.py`
- Modify: `api/admin/router.py`

- [ ] **Step 1: Write failing tests**

Add to `api/tests/test_audit.py`:

```python
async def test_login_failure_logged(client):
    """Failed login attempt writes an auth.login_failure audit event."""
    from db.database import async_session_maker, create_db
    from db.models import AuditLog
    from sqlalchemy import select
    import auth.users  # noqa

    await create_db()
    await client.post("/auth/jwt/login", data={
        "username": "nonexistent@example.com",
        "password": "wrongpassword",
    })

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "auth.login_failure")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.actor_email == "nonexistent@example.com"


async def test_admin_audit_log_endpoint(editor_client):
    """GET /admin/audit-log returns audit events (admin only)."""
    from tests.conftest import create_test_user
    from db.database import create_db
    import auth.users  # noqa
    from httpx import AsyncClient, ASGITransport
    from main import app

    await create_db()
    await create_test_user("audit_admin@test.com", "Securepass1!", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "audit_admin@test.com", "password": "Securepass1!"})
        token = r.json()["access_token"]
        r = await c.get("/admin/audit-log", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data


async def test_admin_audit_log_requires_admin(editor_client):
    """Non-admin users cannot access /admin/audit-log."""
    r = await editor_client.get("/admin/audit-log")
    assert r.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_audit.py -k "login_failure or audit_log_endpoint"
```

Expected: FAIL.

- [ ] **Step 3: Add login failure middleware to main.py**

Add before the route includes:

```python
import urllib.parse
from starlette.middleware.base import BaseHTTPMiddleware

class LoginFailureAuditMiddleware(BaseHTTPMiddleware):
    """Intercepts failed login responses (HTTP 400) and writes audit.login_failure events.

    IMPORTANT: request.body() must be called BEFORE call_next() to populate Starlette's
    body cache. If called after, the receive stream is already exhausted by the route
    handler and the body read will return empty bytes in production (real HTTP).
    """

    async def dispatch(self, request, call_next):
        # Buffer the body BEFORE dispatching to downstream handler
        if request.method == "POST" and request.url.path == "/auth/jwt/login":
            await request.body()  # populates internal cache; downstream can still read it

        response = await call_next(request)

        if request.method == "POST" and request.url.path == "/auth/jwt/login" and response.status_code == 400:
            try:
                body = await request.body()  # safe: reads from cache populated above
                parsed = urllib.parse.parse_qs(body.decode())
                # fastapi-users uses 'username' field for the email address
                raw_email = parsed.get("username", ["unknown"])
                email = urllib.parse.unquote_plus(raw_email[0]) if raw_email else "unknown"
            except Exception:
                email = "unknown"

            ip = request.client.host if request.client else None
            from db.database import async_session_maker
            from audit.service import log_event
            async with async_session_maker() as session:
                await log_event(session, actor_email=email, action="auth.login_failure", ip=ip)

        return response

app.add_middleware(LoginFailureAuditMiddleware)
```

- [ ] **Step 4: Add GET /admin/audit-log endpoint to admin/router.py**

```python
from db.models import AuditLog
from sqlalchemy import select, func

@router.get("/audit-log")
async def get_audit_log(
    page: int = 1,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    offset = (page - 1) * limit
    total = (await session.execute(select(func.count()).select_from(AuditLog))).scalar() or 0
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
    )
    items = result.scalars().all()
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "actor_email": row.actor_email,
                "action": row.action,
                "target": row.target,
                "detail": row.detail,
                "ip_address": row.ip_address,
            }
            for row in items
        ],
    }
```

- [ ] **Step 5: Build and run all tests**

```bash
make build-api && make pytest
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add api/main.py api/admin/router.py api/tests/test_audit.py
git commit -m "feat: add login-failure audit middleware and GET /admin/audit-log endpoint"
```

---

## Task 13: Dockerfile and Caddy Hardening (spec 1.9, 1.10)

**Files:**
- Modify: `api/Dockerfile`
- Modify: `docker-compose.test.yml`
- Modify: `caddy/Caddyfile`

- [ ] **Step 1: Remove --reload from production Dockerfile**

In `api/Dockerfile`, change the CMD line:
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Add --reload override in docker-compose.test.yml**

```yaml
services:
  api:
    build: ./api
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./vault-test:/vault
      ...
```

- [ ] **Step 3: Rebuild and verify test environment still starts**

```bash
make build-api
./start.sh --test
```

Wait for the API to be ready, then: `curl http://localhost:8081/kms/api/health` — expect `{"status":"ok"}`.

- [ ] **Step 4: Update caddy/Caddyfile with security headers and TLS hooks**

Replace the entire contents:

```
{$CADDY_DOMAIN:localhost}:{$CADDY_PORT:8080} {
    # TLS mode controlled by CADDY_TLS_MODE env var:
    #   auto:     tls {$CADDY_EMAIL}    (Let's Encrypt, requires real domain)
    #   internal: tls internal          (self-signed, LAN use)
    #   off:      (omit tls line)       (plain HTTP, current default)

    header {
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
        # HSTS: only uncomment when CADDY_TLS_MODE is auto or internal
        # Strict-Transport-Security "max-age=31536000; includeSubDomains"
        # CSP GATE: uncomment ONLY after the UI inline-style sweep (spec 1.12) is complete
        # Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'"
    }

    handle /kms/api/* {
        uri strip_prefix /kms/api
        reverse_proxy api:8000
    }

    handle /kms* {
        uri strip_prefix /kms
        reverse_proxy ui:80
    }
}
```

- [ ] **Step 5: Verify Caddy reloads cleanly**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test restart caddy
docker compose -f docker-compose.test.yml --env-file .env.test logs caddy --tail 20
```

Expected: No errors. `curl -I http://localhost:8081/kms/api/health` should show `X-Frame-Options: DENY` in the response headers.

- [ ] **Step 6: Run all tests**

```bash
make pytest
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add api/Dockerfile docker-compose.test.yml caddy/Caddyfile
git commit -m "feat: remove --reload from prod uvicorn, add Caddy security headers and TLS hooks"
```

---

## Task 14: Final Cleanup and E2E Smoke (spec remaining)

**Files:**
- Modify: `.env.example`
- Modify: `.env.test`

- [ ] **Step 1: Update .env.example with all new vars**

```
SECRET_KEY=<generate with: openssl rand -hex 32>
VAULT_PATH=/vault
OLLAMA_URL=http://ollama:11434
DATABASE_URL=sqlite+aiosqlite:////data/kb.db
CHROMADB_PATH=/data/chroma
MAILGUN_WEBHOOK_SIGNING_KEY=
INGEST_EMAIL_WHITELIST=
APP_VERSION=unknown
ALLOWED_ORIGINS=http://localhost:8080
ENABLE_API_DOCS=false
CADDY_TLS_MODE=off
CADDY_DOMAIN=localhost
CADDY_PORT=8080
CADDY_EMAIL=
```

- [ ] **Step 2: Ensure .env.test has required values**

```
SECRET_KEY=test-secret-key-placeholder-32ch
VAULT_PATH=/vault
OLLAMA_URL=http://host.docker.internal:11434
DATABASE_URL=sqlite+aiosqlite:////data/kb.db
CHROMADB_PATH=/data/chroma
MAILGUN_WEBHOOK_SIGNING_KEY=
INGEST_EMAIL_WHITELIST=
APP_VERSION=dev
ALLOWED_ORIGINS=http://localhost:8081
ENABLE_API_DOCS=true
```

- [ ] **Step 3: Run full backend test suite**

```bash
make pytest
```

Expected: All tests pass.

- [ ] **Step 4: Run E2E tests**

```bash
make e2e
```

Expected: All E2E tests pass (or same pre-existing failures as before this PR).

- [ ] **Step 5: Manual smoke check — verify security headers**

```bash
curl -I http://localhost:8081/kms/api/health
```

Expected output includes:
```
x-frame-options: DENY
x-content-type-options: nosniff
referrer-policy: strict-origin-when-cross-origin
permissions-policy: camera=(), microphone=(), geolocation=()
```
And does NOT include `server:` header.

- [ ] **Step 6: Manual smoke check — verify /api-docs is accessible in test (ENABLE_API_DOCS=true)**

`curl http://localhost:8081/kms/api/api-docs` — expect 200 with Swagger HTML.

- [ ] **Step 7: Commit and push**

```bash
git add .env.example .env.test
git commit -m "chore: update env examples with Phase 1 security vars"
git push origin HEAD
```

Create PR against `main`.

---

## What Comes Next

**Plan 1B (separate PR):** UI inline-style sweep (`ui/src/**`) — extract all `style={{...}}` props to CSS files. Once complete, uncomment the `Content-Security-Policy` line in `caddy/Caddyfile`.

**Plan 2 (separate PR):** Phase 2 infrastructure and session hardening — non-root Docker users, network segmentation, read-only containers, Docker secrets, encrypted backups with `age`, JWT → httpOnly cookie.

See `docs/superpowers/plans/2026-03-09-security-hardening-phase2.md`.
