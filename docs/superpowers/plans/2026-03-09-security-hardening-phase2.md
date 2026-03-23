# Security Hardening Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the infrastructure layer and replace the XSS-vulnerable localStorage JWT with a server-controlled httpOnly cookie, completing the full security hardening spec.

**Architecture:** Docker Compose changes for network segmentation and non-root containers; `age` encryption for backups; FastAPI CookieTransport replacing BearerTransport; React auth context replacing localStorage.

**Tech Stack:** Docker Compose, Python FastAPI, fastapi-users 13 CookieTransport, React + TypeScript, `age` (backup encryption tool), bash.

**Prerequisite:** Phase 1 plan (`2026-03-09-security-hardening-phase1.md`) must be merged to `main` and deployed to test before starting this plan. Phase 2 builds on Phase 1's `model_validator`, `Settings` fields, and test fixtures.

**Spec:** `docs/superpowers/specs/2026-03-09-security-hardening-design.md` §§ 2.1–2.9

**How to run tests:**
```bash
make build-api        # after backend changes
make build-ui         # after frontend changes
make pytest           # backend unit/integration tests
make e2e              # Playwright E2E tests (test env must be running)
```

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `api/Dockerfile` | Modify | Add non-root `appuser` |
| `api/entrypoint.sh` | Create | Fix volume permissions before uvicorn starts |
| `ui/Dockerfile` | Modify | Add `USER nginx` in final stage |
| `docker-compose.yml` | Modify | Network segmentation, read-only containers, Docker secrets, remove extra_hosts |
| `docker-compose.test.yml` | Modify | Network segmentation (same pattern, no secrets) |
| `api/config.py` | Modify | Add `_read_secret()`, `cookie_secure: bool`, Docker secrets wiring |
| `api/auth/users.py` | Modify | Replace BearerTransport with CookieTransport; add `validate_password` |
| `api/admin/router.py` | Modify | Strengthen password check in `reset_password` to 12+ chars |
| `ui/src/api/client.ts` | Modify | Remove localStorage token; add `credentials: "include"`; add `logout()` |
| `ui/src/contexts/AuthContext.tsx` | Create | Auth context from `GET /users/me` instead of localStorage |
| `ui/src/App.tsx` | Modify | Wrap with AuthContext provider |
| `ui/src/pages/Login.tsx` | Modify | Use AuthContext; remove localStorage writes |
| `ui/src/components/NavBar.tsx` | Modify | Use AuthContext for role/email; fix AI poll to include credentials |
| `api/tests/test_audit.py` | Modify | Update `test_admin_audit_log_endpoint` fixture from Bearer to cookie auth |
| `backup.sh` | Modify | Pipe archive through `age` encryption; update prune glob |
| `deploy.sh` | Modify | Verify `AGE_PUBLIC_KEY` before backup |
| `.env.example` | Modify | Add `AGE_PUBLIC_KEY`, `COOKIE_SECURE` |
| `docs/DEPLOYMENT.md` | Modify | Host disk encryption, secrets setup, age key management, Ollama alternative |

---

## Task 1: Non-Root Docker Users + Read-Only Containers (spec 2.1, 2.3)

These two must be implemented together — `USER nginx` requires the tmpfs mounts from 2.3 or the container crashes on startup.

**Files:**
- Modify: `api/Dockerfile`
- Create: `api/entrypoint.sh`
- Modify: `ui/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.test.yml`

- [ ] **Step 1: Update api/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser

# Entrypoint fixes volume permissions before dropping to appuser
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create api/entrypoint.sh**

The entrypoint runs as root, fixes ownership on mounted volumes, then drops to `appuser`:

```bash
#!/bin/sh
set -e

# Fix ownership on volumes that are mounted as root
chown -R appuser:appuser /vault /data 2>/dev/null || true

exec gosu appuser "$@"
```

**Note:** Use `gosu`, not `su-exec`. `su-exec` is an Alpine package only — `python:3.12-slim` is Debian-based and `apt-get install su-exec` will fail with "Unable to locate package". `gosu` is the standard Debian equivalent. Add it to the Dockerfile before the `COPY . .` line:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Update ui/Dockerfile and nginx.conf**

Setting `USER nginx` in the Dockerfile causes the nginx master process to start as the `nginx` user. That user cannot bind to port 80 (privileged port, requires root or `CAP_NET_BIND_SERVICE`). The fix: change nginx to listen on port 8080 (unprivileged) and update the Caddy reverse proxy target to match.

**Read `ui/nginx.conf` first.** Then update the `listen` directive from `80` to `8080`:

```nginx
server {
    listen 8080;
    # ... rest of config unchanged
}
```

Update `docker-compose.yml` and `docker-compose.test.yml` — in the Caddy Caddyfile and compose `depends_on`, the UI is referenced as `ui:80`. Change both Caddyfiles' reverse_proxy line from `ui:80` to `ui:8080`.

- [ ] **Step 3b: Update both Caddyfiles to proxy to ui:8080**

In `caddy/Caddyfile`, find the line:
```
        reverse_proxy ui:80
```
Replace with:
```
        reverse_proxy ui:8080
```

Do the same in `caddy/Caddyfile.test`:
```
        reverse_proxy ui:8080
```

Then update `ui/Dockerfile`:

```dockerfile
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER nginx
EXPOSE 8080
```

- [ ] **Step 4: Add network segmentation and tmpfs to docker-compose.yml**

Replace the existing docker-compose.yml:

```yaml
networks:
  frontend:
  backend:

secrets:
  secret_key:
    file: ${HOME}/.kms-secrets/secret_key
  mailgun_signing_key:
    file: ${HOME}/.kms-secrets/mailgun_signing_key

services:
  api:
    build: ./api
    networks:
      - frontend
      - backend
    volumes:
      - ./vault:/vault
      - kb_data:/data
    tmpfs:
      - /tmp
    env_file: .env
    environment:
      - APP_VERSION
    secrets:
      - secret_key
      - mailgun_signing_key
    depends_on:
      - chromadb

  ui:
    build: ./ui
    networks:
      - frontend
    read_only: true
    tmpfs:
      - /tmp
      - /var/cache/nginx
      - /var/run

  chromadb:
    image: chromadb/chroma:latest
    networks:
      - backend
    volumes:
      - kb_data:/chroma/chroma

  caddy:
    image: caddy:2-alpine
    networks:
      - frontend
    ports:
      - "8080:8080"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    tmpfs:
      - /tmp

volumes:
  kb_data:
  caddy_data:
```

- [ ] **Step 5: Apply network segmentation to docker-compose.test.yml**

```yaml
networks:
  frontend:
  backend:

services:
  api:
    build: ./api
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - frontend
      - backend
    volumes:
      - ./vault-test:/vault
      - kb_data_test:/data
    env_file: .env.test
    environment:
      - APP_VERSION
    depends_on:
      - chromadb
    extra_hosts:
      - "host.docker.internal:host-gateway"

  ui:
    build: ./ui
    networks:
      - frontend
    read_only: true
    tmpfs:
      - /tmp
      - /var/cache/nginx
      - /var/run

  chromadb:
    image: chromadb/chroma:latest
    networks:
      - backend
    volumes:
      - kb_data_test:/chroma/chroma

  caddy:
    image: caddy:2-alpine
    networks:
      - frontend
    ports:
      - "8081:8081"
    volumes:
      - ./caddy/Caddyfile.test:/etc/caddy/Caddyfile
      - caddy_data_test:/data

volumes:
  kb_data_test:
  caddy_data_test:
```

Note: test stack keeps `extra_hosts` (Ollama on host), no Docker secrets (test uses .env.test).

- [ ] **Step 6: Build and start test stack**

```bash
make build && ./start.sh --test
```

Watch logs for errors:
```bash
make logs-api
docker compose -f docker-compose.test.yml --env-file .env.test logs ui --tail 20
```

Expected: API starts, nginx starts, no permission errors.

- [ ] **Step 7: Run tests**

```bash
make pytest && make e2e
```

Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add api/Dockerfile api/entrypoint.sh ui/Dockerfile docker-compose.yml docker-compose.test.yml
git commit -m "feat: non-root Docker users, network segmentation, read-only UI container"
```

---

## Task 2: Remove extra_hosts from Prod + Document Ollama Alternative (spec 2.4)

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Remove extra_hosts from docker-compose.yml**

The `extra_hosts: host.docker.internal:host-gateway` block was already absent from the Task 1 docker-compose.yml above. Confirm it is not present.

- [ ] **Step 2: Add Ollama section to DEPLOYMENT.md**

Add under a "Ollama Configuration" section:

```markdown
## Ollama Configuration

Prod no longer routes to `host.docker.internal`. If Ollama runs on the same host:

- **Option A (recommended):** Run Ollama as a Docker container in a third network `ollama-net`, connect the `api` service to it, and set `OLLAMA_URL=http://ollama:11434`.
- **Option B:** Set `OLLAMA_URL` to the host's LAN IP (e.g. `http://192.168.1.10:11434`). Do not use `host.docker.internal` in prod.
- **Option C:** If Ollama is not used, set `OLLAMA_URL` to any unreachable URL — the app starts without it and degrades gracefully.
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml docs/DEPLOYMENT.md
git commit -m "chore: remove extra_hosts from prod, document Ollama alternatives"
```

---

## Task 3: Docker Secrets for Sensitive Config (spec 2.5)

**Files:**
- Modify: `api/config.py`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Write failing test**

Add to `api/tests/test_security.py`:

```python
def test_read_secret_from_file(tmp_path):
    """_read_secret() reads from a Docker secrets file path when it exists."""
    secret_file = tmp_path / "my_secret"
    secret_file.write_text("file-based-secret-value\n")

    # _read_secret is a plain function — call it directly with the file path
    from config import _read_secret
    result = _read_secret(str(secret_file), "fallback")
    assert result == "file-based-secret-value"


def test_read_secret_falls_back_when_file_missing():
    """_read_secret() returns the fallback when the secrets file does not exist."""
    from config import _read_secret
    result = _read_secret("/run/secrets/nonexistent_xyz_12345", "my-fallback")
    assert result == "my-fallback"
```

**Note:** `_read_secret` is a plain function — no `__wrapped__` needed. The first argument is a full path (e.g., `/run/secrets/secret_key`); in tests, pass a `tmp_path`-based path to a real file.

The `_read_secret` signature accepts a full path for the secrets file. In `config.py`, it is called with `/run/secrets/<name>`. In tests, pass a path to a temp file. The function must be written to accept any path (not just `/run/secrets/` paths) for this to be testable:

```python
def _read_secret(path: str, fallback: str) -> str:
    """Read a secret from a file path, falling back to the provided default.
    In production, path is /run/secrets/<name> (Docker secrets mount point).
    """
    from pathlib import Path
    secret_path = Path(path)
    if secret_path.exists():
        return secret_path.read_text().strip()
    return fallback
```

The call sites in `settings = Settings(...)` use full paths:
```python
settings = Settings(
    secret_key=_read_secret("/run/secrets/secret_key", os.environ.get("SECRET_KEY", "changeme")),
    mailgun_webhook_signing_key=_read_secret("/run/secrets/mailgun_signing_key", os.environ.get("MAILGUN_WEBHOOK_SIGNING_KEY", "")),
)
```

- [ ] **Step 2: Add `_read_secret` and update Settings construction in config.py**

```python
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import model_validator


def _read_secret(path: str, fallback: str) -> str:
    """Read a secret from a file path, falling back to the provided default.

    In production: path is /run/secrets/<name> (Docker secrets mount).
    In tests: path is any file path (e.g. tmp_path from pytest).
    Accepts a full path — does NOT prepend /run/secrets/ automatically.
    """
    secret_path = Path(path)
    if secret_path.exists():
        return secret_path.read_text().strip()
    return fallback


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
    cookie_secure: bool = True  # set False in .env.test for HTTP test env

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        if self.secret_key in ("changeme", "") or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY is insecure. Generate one with: openssl rand -hex 32"
            )
        return self

    class Config:
        env_file = ".env"


# Resolve secrets from Docker secrets files first, then fall back to env vars.
# _read_secret runs before Settings() so the model_validator sees the resolved value.
settings = Settings(
    secret_key=_read_secret("/run/secrets/secret_key", os.environ.get("SECRET_KEY", "changeme")),
    mailgun_webhook_signing_key=_read_secret("/run/secrets/mailgun_signing_key", os.environ.get("MAILGUN_WEBHOOK_SIGNING_KEY", "")),
)
```

- [ ] **Step 3: Add COOKIE_SECURE=false to .env.test**

```
COOKIE_SECURE=false
```

- [ ] **Step 4: Document secrets setup in DEPLOYMENT.md**

Add a "Secrets Setup" section:

```markdown
## Secrets Setup (Production)

Create the secrets directory on the host (never commit these files):

```bash
mkdir -p ~/.kms-secrets
chmod 700 ~/.kms-secrets
openssl rand -hex 32 > ~/.kms-secrets/secret_key
chmod 600 ~/.kms-secrets/secret_key
# If using Mailgun:
echo "your-mailgun-signing-key" > ~/.kms-secrets/mailgun_signing_key
chmod 600 ~/.kms-secrets/mailgun_signing_key
```

Docker Compose reads these via the `secrets:` block using `${HOME}` expansion.

> **WARNING:** If `~/.kms-secrets/secret_key` is lost, all existing JWTs are immediately invalid. Back up this file in a password manager.
```

- [ ] **Step 5: Build and run tests**

```bash
make build-api && make pytest
```

Expected: All pass. The validator still works because `_read_secret` falls back to the env var value from conftest.

- [ ] **Step 6: Commit**

```bash
git add api/config.py .env.test docs/DEPLOYMENT.md
git commit -m "feat: add Docker secrets reader, cookie_secure setting, update deployment docs"
```

---

## Task 4: Encrypted Backups with `age` (spec 2.6)

**Files:**
- Modify: `backup.sh`
- Modify: `deploy.sh`
- Modify: `.env.example`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Read current backup.sh to understand its structure**

Read `backup.sh` fully before editing. Identify:
- Where the tar archive is created
- Any existing prune/rotation logic and the glob it uses

- [ ] **Step 2: Update backup.sh**

After the tar creation line, add age encryption:

```bash
# Encrypt the backup archive
if [ -z "$AGE_PUBLIC_KEY" ]; then
    echo "WARNING: AGE_PUBLIC_KEY not set — backup stored unencrypted"
else
    if ! command -v age &>/dev/null; then
        echo "ERROR: 'age' not installed. Run: sudo apt install age"
        exit 1
    fi
    age -r "$AGE_PUBLIC_KEY" < "$ARCHIVE_PATH" > "${ARCHIVE_PATH}.age"
    rm "$ARCHIVE_PATH"
    ARCHIVE_PATH="${ARCHIVE_PATH}.age"
    echo "Backup encrypted: $ARCHIVE_PATH"
fi
```

Update any prune/rotation glob from `*.tar.gz` to handle both `.tar.gz` and `.tar.gz.age`:

```bash
# Prune backups older than 30 days
find "${BACKUP_DIR}" -name "*.tar.gz.age" -mtime +30 -delete
find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +30 -delete
```

- [ ] **Step 3: Update deploy.sh to warn if AGE_PUBLIC_KEY is not set**

Before calling backup.sh, add:

```bash
if [ -z "$AGE_PUBLIC_KEY" ]; then
    echo "WARNING: AGE_PUBLIC_KEY is not set. Backups will be stored unencrypted."
    read -p "Continue anyway? [y/N] " confirm
    [ "$confirm" = "y" ] || exit 1
fi
```

- [ ] **Step 4: Add AGE_PUBLIC_KEY to .env.example**

```
AGE_PUBLIC_KEY=<your age public key — generate with: age-keygen>
```

- [ ] **Step 5: Document age key management in DEPLOYMENT.md**

```markdown
## Encrypted Backups

Backups are encrypted with `age` (https://age-encryption.org). Install:
```bash
sudo apt install age   # Ubuntu 22+
```

Generate a keypair:
```bash
age-keygen -o ~/.kms-secrets/age-key.txt
```
The output contains your public key (starts with `age1...`) and private key.

Set `AGE_PUBLIC_KEY=age1...` in your `.env` file (the public key is not sensitive).

**Store the private key securely:** if `~/.kms-secrets/age-key.txt` is lost, all encrypted backups are permanently unreadable. Save it in a password manager and consider a printed copy stored offline.

To decrypt a backup:
```bash
age -d -i ~/.kms-secrets/age-key.txt backup.tar.gz.age | tar -xz
```
```

- [ ] **Step 6: Manual test of backup**

```bash
# Generate a test key
age-keygen -o /tmp/test-age-key.txt
export AGE_PUBLIC_KEY=$(grep "public key" /tmp/test-age-key.txt | awk '{print $NF}')

./backup.sh --env test
ls backups/   # should show .tar.gz.age file, no unencrypted .tar.gz

# Verify decryption works
age -d -i /tmp/test-age-key.txt backups/*.tar.gz.age | tar -tz | head -10
```

Expected: Backup file exists as `.tar.gz.age`, and decryption succeeds.

- [ ] **Step 7: Commit**

```bash
git add backup.sh deploy.sh .env.example docs/DEPLOYMENT.md
git commit -m "feat: encrypt backups with age, update deploy guard and docs"
```

---

## Task 5: Host Disk Encryption Documentation (spec 2.7)

**Files:**
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Add host security requirements section to DEPLOYMENT.md**

Add near the top of the deployment guide, before the quickstart:

```markdown
## Host Security Requirements

KMS stores business-confidential data in Docker volumes (`kb_data`, `caddy_data`) on the host filesystem. These volumes are NOT encrypted at the application level — they rely on the host providing encryption.

**Full-disk encryption is required on any host running KMS in production.**

### Verify encryption is enabled (Linux)

```bash
lsblk -o NAME,FSTYPE,MOUNTPOINT,SIZE
```

Look for `crypto_LUKS` on your root/data partition. If absent, enable LUKS at OS install time (cannot be added to an existing partition without data loss).

### Ubuntu setup reference

Full-disk encryption is offered as an option during the Ubuntu Server installer ("Encrypt the LVM group with LUKS"). Select this during initial install.

### What this protects

Docker named volumes (`kb_data`, `caddy_data`) are stored under `/var/lib/docker/volumes/`. With host LUKS encryption, these are unreadable without the host's disk password, protecting:
- SQLite database (users, documents metadata, audit log, version history)
- ChromaDB vector store (document embeddings)
- Vault files (your actual document content)
```

- [ ] **Step 2: Commit**

```bash
git add docs/DEPLOYMENT.md
git commit -m "docs: add host disk encryption requirement to deployment guide"
```

---

## Task 6: Password Strength Enforcement (spec 2.9)

Do this before the cookie migration (Task 7) — it's a small backend change with no frontend dependency.

**Files:**
- Modify: `api/auth/users.py`
- Modify: `api/admin/router.py`

- [ ] **Step 1: Write failing tests**

Add to `api/tests/test_auth.py`:

```python
async def test_weak_password_rejected_on_register(client):
    """Registration rejects passwords shorter than 12 chars or missing digit/special char."""
    r = await client.post("/auth/register", json={
        "email": "weakpass@test.com",
        "password": "short",
        "role": "reader",
    })
    assert r.status_code == 400

    r = await client.post("/auth/register", json={
        "email": "weakpass2@test.com",
        "password": "onlylettersnodigits!",  # no digit
        "role": "reader",
    })
    assert r.status_code == 400

    r = await client.post("/auth/register", json={
        "email": "weakpass3@test.com",
        "password": "onlyletters12345",  # no special char
        "role": "reader",
    })
    assert r.status_code == 400


async def test_strong_password_accepted(client):
    r = await client.post("/auth/register", json={
        "email": "strongpass@test.com",
        "password": "Securepass1!",
        "role": "reader",
    })
    assert r.status_code == 201
```

- [ ] **Step 2: Run to verify they fail**

```bash
make build-api && docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v api/tests/test_auth.py -k "password"
```

Expected: FAIL.

- [ ] **Step 3: Add validate_password to UserManager in users.py**

```python
from fastapi_users.exceptions import InvalidPasswordException

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def validate_password(self, password: str, user=None) -> None:
        if len(password) < 12:
            raise InvalidPasswordException("Password must be at least 12 characters")
        if not any(c.isdigit() for c in password):
            raise InvalidPasswordException("Password must contain at least one digit")
        if not any(not c.isalnum() for c in password):
            raise InvalidPasswordException("Password must contain at least one special character")

    async def on_after_register(self, user: User, request=None):
        if user.role != "reader":
            await self.user_db.update(user, {"role": "reader"})

    async def on_after_login(self, user: User, request=None, response=None):
        from db.database import async_session_maker
        from audit.service import log_event
        ip = request.client.host if request and request.client else None
        async with async_session_maker() as session:
            await log_event(session, actor_email=user.email, action="auth.login_success", ip=ip)
```

- [ ] **Step 4: Strengthen reset_password in admin/router.py**

Replace the current 8-char check:

```python
# Before:
if len(stripped) < 8:
    raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

# After:
if len(stripped) < 12:
    raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
if not any(c.isdigit() for c in stripped):
    raise HTTPException(status_code=400, detail="Password must contain at least one digit")
if not any(not c.isalnum() for c in stripped):
    raise HTTPException(status_code=400, detail="Password must contain at least one special character")
```

- [ ] **Step 5: Update ALL existing tests that use weak passwords**

Search for any test that registers with passwords like `"pass"`, `"password123"` (no special char), etc., and update them to use `"Securepass1!"`. The `create_test_user()` helper bypasses `validate_password` (it hashes directly), so fixtures using that helper are fine.

```bash
grep -r '"password"' api/tests/ | grep -v "Securepass"
```

Update any matches to use `"Securepass1!"`.

- [ ] **Step 6: Build and run all tests**

```bash
make build-api && make pytest
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add api/auth/users.py api/admin/router.py api/tests/
git commit -m "feat: enforce 12-char password with digit and special char requirement"
```

---

## Task 7: JWT → httpOnly Cookie (spec 2.8)

This is the largest change — replaces the entire auth token transport. Backend and frontend change together. Take it in three steps: backend first, then frontend client, then auth context.

**Files:**
- Modify: `api/auth/users.py`
- Modify: `api/ingestion/router.py` — update `_key_by_user` to read cookie instead of Bearer header
- Modify: `api/tests/conftest.py`
- Modify: `api/tests/test_auth.py`
- Modify: `api/tests/test_docs.py`
- Modify: `api/tests/test_admin.py`
- Modify: `ui/src/api/client.ts`
- Create: `ui/src/contexts/AuthContext.tsx`
- Modify: `ui/src/App.tsx`
- Modify: `ui/src/pages/Login.tsx`
- Modify: `ui/src/components/NavBar.tsx`

### 7a: Backend — Switch to CookieTransport

- [ ] **Step 1: Update auth/users.py**

Replace `BearerTransport` with `CookieTransport`:

```python
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from config import settings

cookie_transport = CookieTransport(
    cookie_name="kmstoken",
    cookie_max_age=3600,
    cookie_secure=settings.cookie_secure,   # False in test (HTTP), True in prod (HTTPS)
    cookie_httponly=True,
    cookie_samesite="strict",
    cookie_path="/kms/api",
)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.secret_key, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
```

Remove the `BearerTransport` import and the old `bearer_transport` variable.

- [ ] **Step 1b: Update `_key_by_user` in ingestion/router.py to read cookie**

The per-user rate limit key function currently reads the `Authorization` Bearer header. After the cookie migration it will always fall through to the IP fallback. Update it to read the `kmstoken` cookie instead:

```python
# In api/ingestion/router.py — replace the existing _key_by_user function
from jose import jwt as jose_jwt, JWTError

def _key_by_user(request: Request) -> str:
    token = request.cookies.get("kmstoken", "")
    if token:
        try:
            payload = jose_jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            return payload.get("sub") or get_remote_address(request)
        except JWTError:
            pass
    return get_remote_address(request)
```

- [ ] **Step 2: Update test infrastructure for cookie-based auth**

Backend tests use `httpx.AsyncClient` with `ASGITransport`. The httpx client handles `Set-Cookie` headers automatically — but only if the subsequent request's path matches the cookie's `Path` attribute.

**Cookie path mismatch:** `CookieTransport` sets `cookie_path="/kms/api"`. Test clients make requests to paths like `/docs`, `/admin/audit-log` (no `/kms/api` prefix). The httpx cookie jar will NOT send the cookie on those requests, causing spurious 401s in tests.

**Fix:** Use a test-environment override of `cookie_path`. Add `cookie_secure: bool = True` and `cookie_path: str = "/kms/api"` to `config.py`. In `.env.test`, set `COOKIE_PATH=/` so the cookie is sent on all paths in the test client. Update `CookieTransport` to read `settings.cookie_path`:

```python
cookie_transport = CookieTransport(
    cookie_name="kmstoken",
    cookie_max_age=3600,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite="strict",
    cookie_path=settings.cookie_path,   # "/" in test, "/kms/api" in prod
)
```

Add to `config.py`: `cookie_path: str = "/kms/api"`
Add to `.env.test`: `COOKIE_PATH=/`

Update `conftest.py` to add a login helper:

```python
async def login_client(client, email: str, password: str) -> None:
    """Log in via POST /auth/jwt/login — cookie is stored automatically by httpx."""
    r = await client.post("/auth/jwt/login", data={"username": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
```

Also update `test_audit.py` — the `test_admin_audit_log_endpoint` fixture currently extracts `r.json()["access_token"]` and sets a Bearer header. Replace with the cookie pattern (login, then use the client directly without setting any auth header):

```python
async def test_admin_audit_log_endpoint(editor_client):
    from tests.conftest import create_test_user
    from db.database import create_db
    import auth.users  # noqa
    from httpx import AsyncClient, ASGITransport
    from main import app

    await create_db()
    await create_test_user("audit_admin@test.com", "Securepass1!", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/jwt/login", data={"username": "audit_admin@test.com", "password": "Securepass1!"})
        # Cookie stored automatically — no Authorization header needed
        r = await c.get("/admin/audit-log")
        assert r.status_code == 200
```

- [ ] **Step 3: Update test fixtures in test_docs.py, test_admin.py, test_security.py**

Replace fixtures that extract `access_token` with cookie-based equivalents:

```python
# Before (bearer):
@pytest.fixture
async def editor_client():
    await create_test_user("ed@test.com", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c

# After (cookie):
@pytest.fixture
async def editor_client():
    import auth.users  # noqa
    from db.database import create_db
    await create_db()
    await create_test_user("ed@test.com", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "Securepass1!"})
        # Cookie is stored automatically by httpx — no header manipulation needed
        yield c
```

Apply this pattern to ALL fixtures in ALL test files that currently do `token = r.json()["access_token"]` and `c.headers["Authorization"] = f"Bearer {token}"`.

- [ ] **Step 4: Update test_auth.py**

The `test_register_and_login` test checks `"access_token" in r.json()`. After switching to CookieTransport, the login response no longer returns JSON with `access_token` — it sets a cookie. Update:

```python
async def test_register_and_login(client):
    r = await client.post("/auth/register", json={
        "email": "alice@example.com",
        "password": "Securepass1!",
        "role": "editor",
    })
    assert r.status_code == 201

    r = await client.post("/auth/jwt/login", data={
        "username": "alice@example.com",
        "password": "Securepass1!",
    })
    assert r.status_code == 200
    # Cookie transport: token is in Set-Cookie, not JSON body
    assert "kmstoken" in r.cookies or "set-cookie" in r.headers
```

- [ ] **Step 5: Build and run all backend tests**

```bash
make build-api && make pytest
```

Expected: All pass. If any test still references `access_token` in JSON, it will fail — find and fix it.

- [ ] **Step 6: Commit backend changes**

```bash
git add api/auth/users.py api/ingestion/router.py api/tests/
git commit -m "feat: switch JWT transport to httpOnly cookie (CookieTransport)"
```

### 7b: Frontend — Update API Client

- [ ] **Step 7: Update ui/src/api/client.ts**

Read the current `client.ts` fully before editing. Then:

- Remove all `localStorage.getItem("token")`, `localStorage.setItem("token", ...)`, `localStorage.removeItem("token")` calls
- Remove manual `Authorization: Bearer` header injection from fetch calls
- Add `credentials: "include"` to every fetch call (required for browser to send httpOnly cookie cross-path)
- Add a `logout()` function that calls `DELETE /auth/jwt/logout`

Example skeleton:

```typescript
const BASE = "/kms/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    credentials: "include",  // send httpOnly cookie on every request
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/auth/jwt/logout`, {
    method: "DELETE",
    credentials: "include",
  });
}

// All other API functions use request() — remove Bearer header injection
```

- [ ] **Step 8: Create ui/src/contexts/AuthContext.tsx**

```typescript
import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthUser {
  email: string;
  role: string;
  id: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  setUser: (u: AuthUser | null) => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  setUser: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch current user from /users/me on mount
    fetch("/kms/api/users/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setUser({ email: data.email, role: data.role, id: data.id });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
```

- [ ] **Step 9: Wrap App with AuthProvider in App.tsx**

```tsx
import { AuthProvider } from "./contexts/AuthContext";

function App() {
  return (
    <AuthProvider>
      <Router basename="/kms">
        {/* existing routes */}
      </Router>
    </AuthProvider>
  );
}
```

- [ ] **Step 10: Update Login.tsx**

On successful login, instead of storing token in localStorage, call `setUser` from context:

```tsx
import { useAuth } from "../contexts/AuthContext";

export function Login() {
  const { setUser } = useAuth();

  async function handleLogin(email: string, password: string) {
    const res = await fetch("/kms/api/auth/jwt/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!res.ok) { /* show error */ return; }

    // Fetch user info after login (cookie is now set)
    const me = await fetch("/kms/api/users/me", { credentials: "include" }).then(r => r.json());
    setUser({ email: me.email, role: me.role, id: me.id });
    navigate("/");
  }
  // Remove all localStorage references
}
```

- [ ] **Step 11: Update NavBar.tsx**

Replace `localStorage.getItem("role")` / `localStorage.getItem("email")` with `useAuth()`. Fix the AI status poll to include credentials:

```tsx
import { useAuth } from "../contexts/AuthContext";
import { logout } from "../api/client";

export function NavBar() {
  const { user, setUser } = useAuth();

  // AI status poll — must include credentials since /health/ai now requires auth
  useEffect(() => {
    const poll = setInterval(() => {
      fetch("/kms/api/health/ai", { credentials: "include" })
        .then(r => r.json())
        .then(data => setAiStatus(data.ai))
        .catch(() => setAiStatus("offline"));
    }, 30_000);
    return () => clearInterval(poll);
  }, []);

  async function handleLogout() {
    await logout();           // DELETE /auth/jwt/logout — clears httpOnly cookie
    setUser(null);
    navigate("/login");
  }
  // Replace localStorage role checks with user?.role
}
```

- [ ] **Step 12: Build UI and run E2E**

```bash
make build-ui && make e2e
```

Expected: All E2E tests pass. Login, navigation, and logout all work.

- [ ] **Step 13: Manual browser test**

Open `http://localhost:8081/kms`. Log in. Open DevTools → Application → Cookies. Verify:
- Cookie named `kmstoken` exists
- `HttpOnly` is checked
- `SameSite` is `Strict`
- No `kmstoken` visible in `localStorage`

- [ ] **Step 14: Commit frontend changes**

```bash
git add ui/src/
git commit -m "feat: replace localStorage JWT with httpOnly cookie, add AuthContext"
```

---

## Task 8: Final Integration + E2E Verification

- [ ] **Step 1: Run full test suite**

```bash
make pytest && make e2e
```

Expected: All tests pass.

- [ ] **Step 2: Verify Docker network segmentation**

```bash
# UI container should NOT be able to reach ChromaDB directly
docker compose -f docker-compose.test.yml --env-file .env.test exec ui wget -q --timeout=3 http://chromadb:8000 -O - 2>&1
```

Expected: `wget: bad address 'chromadb'` or connection refused — confirms UI is not on `backend` network.

- [ ] **Step 3: Verify API container runs as non-root**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec api whoami
```

Expected: `appuser` (not `root`).

- [ ] **Step 4: Verify UI container is read-only**

```bash
docker compose -f docker-compose.test.yml --env-file .env.test exec ui touch /usr/share/nginx/html/test-write 2>&1
```

Expected: `touch: /usr/share/nginx/html/test-write: Read-only file system`

- [ ] **Step 5: Update DEPLOYMENT.md with full checklist**

Add a "Production Hardening Checklist" section:

```markdown
## Production Hardening Checklist

Before going live, verify:

- [ ] `SECRET_KEY` is 32+ chars, stored in `~/.kms-secrets/secret_key`
- [ ] `~/.kms-secrets/` has `chmod 700`
- [ ] `AGE_PUBLIC_KEY` is set in `.env`
- [ ] Age private key is backed up in a password manager
- [ ] Host OS has full-disk encryption (LUKS)
- [ ] `CADDY_TLS_MODE` is `auto` or `internal` (not `off`)
- [ ] HSTS header uncommented in `caddy/Caddyfile` (the line `# Strict-Transport-Security "max-age=31536000; includeSubDomains"` — remove the leading `#` **only after TLS is confirmed working**; sending HSTS over plain HTTP is harmful)
- [ ] `COOKIE_SECURE` is `true` (default) in prod `.env`
- [ ] `ENABLE_API_DOCS` is not set (defaults `false`)
- [ ] At least one admin account created and tested
- [ ] Backup tested: `./backup.sh --env prod` and verified the `.tar.gz.age` file decrypts
```

- [ ] **Step 6: Commit and push**

```bash
git add docs/DEPLOYMENT.md
git commit -m "docs: add production hardening checklist"
git push origin HEAD
```

Create PR against `main`.
