# Security Hardening Design — KMS
**Date:** 2026-03-09
**Status:** Approved

---

## Context & Threat Model

The Knowledge Management System is currently deployed on a local LAN but will gain a public-facing surface (email ingestion endpoint, and eventually a domain-accessible UI). Users may store business-confidential data including credentials. The system must be hardened against:

- Network-level attackers intercepting traffic (data in motion)
- Attackers with access to the server or backups (data at rest)
- Authenticated-but-low-privilege users escalating access
- Unauthenticated callers abusing public endpoints
- Malicious email content (SQL injection, prompt injection, spam, replay attacks)
- XSS attacks stealing session tokens
- Path traversal attacks from editor-role users

**Sensitivity level:** Business-confidential (B). Users may store credentials, internal strategy, and PII-adjacent content.

**TLS posture:** Design for both domain-backed (Let's Encrypt) and no-domain (self-signed/internal). Config hooks present now; TLS mode switchable via env var.

**Audit logging:** Lightweight DB table recording key actions (not compliance-grade).

---

## Implementation Plan

Two phases. Phase 1 is a single PR targeting critical code vulnerabilities and transport security. Phase 2 is a follow-on PR for infrastructure hardening and session security.

---

## Phase 1 — Critical: Application + Transport

### 1.1 Path Traversal Guard

**Files:** `api/docs_/service.py` and `api/docs_/router.py`

Add a `_safe_path(path: str) -> Path` helper in `service.py` that:
1. Resolves `Path(settings.vault_path) / path` to an absolute path
2. Asserts the resolved path starts with `Path(settings.vault_path).resolve()`
3. Raises `HTTPException(400)` if not

**Import note:** `service.py` does not currently import from `fastapi`. Add `from fastapi import HTTPException` to `service.py` before defining `_safe_path`, or the function will raise a `NameError` at runtime.

Call this at the top of `write_doc_file`, `get_doc`, `update_doc`, and `delete_doc` in `service.py` before any file I/O.

**Also apply in `docs_/router.py`:** The `read` endpoint (GET `/{path:path}`) constructs `full_path = Path(settings.vault_path) / path` and reads the file directly without going through the service layer (lines 56–58). This path bypasses the service-layer guard entirely — an attacker with a valid JWT could call `GET /docs/../../etc/passwd` and read arbitrary host files. Apply `_safe_path(path)` at the top of the `read` endpoint handler, before the vault file is opened. Import `_safe_path` from `docs_.service`.

### 1.2 Block Admin Self-Registration

**File:** `api/auth/users.py`

Override `UserManager.on_after_register` to forcibly reset any submitted role to `"reader"`. At the point this hook fires, the user has already been committed by fastapi-users in its own transaction. The `user` object passed to the hook is a detached ORM instance and must not be re-committed directly. Use `await self.user_db.update(user, {"role": "reader"})` — the `user_db` adapter is already available on `self` and handles the session correctly.

**DI session requirement:** `self.user_db.update()` works correctly only when `UserManager` is obtained through the FastAPI DI chain (`Depends(get_user_manager)`), which provides a `SQLAlchemyUserDatabase` backed by a live async session. Do not instantiate `UserManager` outside the DI chain — the session will be stale. Test this with an integration test that confirms the DB row has `role="reader"` regardless of the submitted value.

The `UserCreate` schema retains the `role` field for admin panel use. Public registration always produces a `reader`. Role promotion goes through `PATCH /admin/users/{id}/role` only.

### 1.3 Role Gate on `POST /ingest`

**File:** `api/ingestion/router.py`

Change dependency from `current_active_user` to `require_editor`. Reader-role users receive HTTP 403.

### 1.4 Rate Limiting

**New dependency:** `slowapi`

**File:** `api/main.py` + individual route files

Apply via `slowapi` limiter:

| Endpoint | Limit | Key |
|---|---|---|
| `POST /auth/jwt/login` | 10/minute | per IP (default `get_remote_address`) |
| `POST /auth/register` | 5/minute | per IP |
| `POST /ingest` | 30/minute | per authenticated user |
| `POST /ingest/email` | 20/minute | per IP |

`POST /ingest` cannot use the default IP-based key (multiple users behind NAT would share a bucket). However, `request.state` set inside the route body is not available when `SlowAPIMiddleware` evaluates the key function on the inbound request — the middleware intercepts before the route handler runs. The correct approach is to decode the JWT directly in the key function:
```python
from jose import jwt as jose_jwt, JWTError

def _key_by_user(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ")
        try:
            payload = jose_jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            return payload.get("sub") or get_remote_address(request)
        except JWTError:
            pass
    return get_remote_address(request)
```
After the Phase 2 cookie migration, replace the `Authorization` header read with reading the cookie: `request.cookies.get("kmstoken", "")`. Apply with `@limiter.limit("30/minute", key_func=_key_by_user)`. **Note:** Do not use `request.state` to pass the user — it will not be populated at key evaluation time.

Add `SlowAPIMiddleware` to `main.py`. Add `RateLimitExceeded` handler returning HTTP 429.

### 1.5 CORS Policy

**File:** `api/main.py`

Add `CORSMiddleware` with:
- `allow_origins`: read from `ALLOWED_ORIGINS` env var (comma-separated). Default: `http://localhost:8080,http://localhost:8081`.
- `allow_credentials=True`
- `allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]`
- `allow_headers=["Authorization", "Content-Type"]`

**File:** `api/config.py`

Add `allowed_origins: str = "http://localhost:8080,http://localhost:8081"`.

### 1.6 Protect API Docs and Health Endpoints

**File:** `api/main.py`

- Change `FastAPI(docs_url=...)` to `docs_url="/api-docs" if settings.enable_api_docs else None` and same for `redoc_url`.
- Add `enable_api_docs: bool = False` to `config.py`.
- Set `ENABLE_API_DOCS=true` in `.env.test` only.
- Add `Depends(current_active_user)` to `GET /health/summary` — it leaks doc/user counts.
- Add `Depends(current_active_user)` to `GET /health/ai` — it reveals whether Ollama is running and reachable from the container network. `/health` (simple liveness) remains public for load-balancer/orchestrator use.

### 1.7 Email Ingestion Hardening

#### Token Deduplication

**New DB model:** `UsedToken(token_hash: String PK, used_at: DateTime)`

Store a SHA-256 hash of the token rather than the raw token — Mailgun tokens are variable-length strings of unspecified length, and hashing avoids unbounded VARCHAR primary keys. `token_hash = hashlib.sha256(token.encode()).hexdigest()` (64 chars, fixed).

**File:** `api/ingestion/router.py`

Before processing an email webhook:
1. Compute `token_hash = sha256(token)`.
2. Check if `token_hash` exists in `UsedToken`. If yes → HTTP 403 "Duplicate request".
3. Insert `UsedToken(token_hash=token_hash, used_at=now())`.
4. Prune entries older than 24 hours using FastAPI `BackgroundTasks` — the prune runs after the response is sent and gets its own DB session via `async_session_maker()`. Do not reuse the request session in the background task.

#### Body Size Cap

Reject requests where `len(body_plain) > 50_000`. Return HTTP 413.

### 1.8 Audit Log

**New DB model:**
```
AuditLog(
    id: Integer PK,
    timestamp: DateTime server_default=now(),
    actor_email: String,       # email of acting user, or "system" / "anonymous"
    action: String,            # e.g. "auth.login_success"
    target: String nullable,   # e.g. doc path, user id
    detail: String nullable,   # freeform JSON string for extra context
    ip_address: String nullable
)
```

**New helper:** `api/audit/service.py` — `async def log_event(session, actor_email, action, target=None, detail=None, ip=None)`

**Events logged:**

| Event | Trigger location |
|---|---|
| `auth.login_success` | `UserManager.on_after_login` |
| `auth.login_failure` | Custom middleware (see note below) |
| `doc.create` | `docs_/router.py` POST |
| `doc.update` | `docs_/router.py` PUT |
| `doc.delete` | `docs_/router.py` DELETE |
| `user.role_change` | `admin/router.py` PATCH role |
| `user.delete` | `admin/router.py` DELETE |
| `user.password_reset` | `admin/router.py` POST reset-password |
| `ingest.email` | `ingestion/router.py` POST /email (log sender + subject only, not body) |

**New endpoint:** `GET /admin/audit-log?page=1&limit=50` — admin-only, returns paginated `AuditLog` rows newest-first.

**Note on `auth.login_failure`:** fastapi-users does not expose an `on_failed_login` hook. Failed logins must be captured differently. Add a thin ASGI middleware in `main.py` that intercepts `POST /auth/jwt/login` responses with status 400 (fastapi-users returns 400 on bad credentials).

Implementation notes:
- In Starlette 0.27+, calling `await request.body()` caches the result on the `Request` object internally. You do not need to write a custom `receive` closure — a simple `await request.body()` in the middleware is sufficient and the downstream route handler will still be able to read the body.
- The login endpoint accepts `application/x-www-form-urlencoded`. Parse the buffered body with `urllib.parse.parse_qs(body.decode())` and extract `username` (fastapi-users uses the `username` field for email). Apply `urllib.parse.unquote_plus` to handle encoded characters. If the body is empty or malformed, default `actor_email` to `"unknown"`.
- Call `log_event(action="auth.login_failure", actor_email=attempted_email, ip=request.client.host)` after the response is confirmed 400.
- Implement and integration-test this middleware independently before wiring to the audit log.

### 1.9 TLS Config Hooks in Caddy

**New env var:** `CADDY_TLS_MODE` — values: `off` (default), `internal`, `auto`
**New env var:** `CADDY_DOMAIN` — hostname for `auto` mode

**File:** `caddy/Caddyfile`

```
{$CADDY_DOMAIN:localhost}:{$CADDY_PORT:8080} {
    # TLS block injected per CADDY_TLS_MODE:
    # auto:     tls {$CADDY_EMAIL}
    # internal: tls internal
    # off:      (no tls block — default)

    header {
        # HSTS is only effective over HTTPS. Only emit when TLS is enabled.
        # When CADDY_TLS_MODE=off, the Caddyfile template must omit this line.
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        # CSP GATE: add the line below ONLY after 1.12 (inline style sweep) is complete.
        # Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
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

**HSTS conditional:** The Caddyfile is templated (via env vars). When `CADDY_TLS_MODE=off`, the `Strict-Transport-Security` header block must be omitted — sending HSTS over plain HTTP has no security effect and can cause browser preload issues if TLS is later misconfigured. Use a Caddyfile snippet or separate `Caddyfile.tls` that is included conditionally from the compose file's `volumes` override.

**CSP gate:** The `Content-Security-Policy` line ships commented out. It is uncommented as a separate commit only after the inline-style sweep (1.12) is verified complete — removing `'unsafe-inline'` from a live UI with inline styles will break all styling.

When `CADDY_TLS_MODE=auto` or `internal`, add a second site block redirecting `http://` → `https://`.

The test `Caddyfile.test` stays on plain HTTP with no headers block (to keep test setup simple).

### 1.10 Remove `--reload` from Production Uvicorn

**File:** `api/Dockerfile`

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**File:** `docker-compose.test.yml`

Override CMD to add `--reload` for test/dev:
```yaml
command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 1.11 Secret Key Startup Validation

**File:** `api/config.py`

The secret key validation must run after the secret value is fully resolved (including Docker secrets, added in 2.5). To avoid ordering issues between Phase 1 and Phase 2, integrate the validation as a pydantic `model_validator` inside `Settings` rather than a block after `settings = Settings()`. This ensures the check runs regardless of whether the value came from an env var or a Docker secrets file:

```python
from pydantic import model_validator

class Settings(BaseSettings):
    ...
    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        if self.secret_key in ("changeme", "") or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY is insecure. Generate one with: openssl rand -hex 32"
            )
        return self
```

In Phase 2, the `_read_secret()` helper populates `secret_key` before `Settings()` is constructed (passed as an override), so the validator will see the resolved value.

**File:** `.env.example`

```
SECRET_KEY=<generate with: openssl rand -hex 32>
```

**File:** `.env.test`

Set a valid 32-char test key (placeholder, tracked in git — acceptable for test env).

### 1.12 UI Inline Style/Script Elimination

**Scope:** All files under `ui/src/`

This is a significant refactor — CLAUDE.md notes "UI uses inline styles" as a pervasive pattern across all components. It may warrant its own PR separate from the other Phase 1 items, delivered after the rest of Phase 1 merges.

Audit every component for:
- `style={{...}}` props → extract to `.css` class
- Inline `<script>` tags → none expected, but verify
- `dangerouslySetInnerHTML` → audit for XSS risk

Extract styles into `ui/src/styles/` directory with one CSS file per component or a shared `global.css`. This is a **prerequisite** for deploying the `Content-Security-Policy` header — the header is added to the Caddyfile (and its git-commented CSP line uncommented) only after this sweep is confirmed clean in both the test environment and a browser audit (DevTools Console must show zero CSP violations).

---

## Phase 2 — Infrastructure + Session Hardening

### 2.1 Non-Root Docker Users

**File:** `api/Dockerfile`
```dockerfile
RUN adduser --disabled-password --gecos "" appuser
USER appuser
```
Adjust volume mount permissions in `docker-compose.yml` to `chown` the `kb_data` volume to this user on first run via an entrypoint script.

**File:** `ui/Dockerfile`
```dockerfile
# final stage
USER nginx
```

**Dependency note:** The `nginx` user cannot write to `/var/cache/nginx`, `/var/run`, or `/tmp` by default. This item depends on 2.3 (read-only containers + tmpfs mounts for those paths). Implement 2.1 and 2.3 together — applying `USER nginx` without the tmpfs mounts will crash the nginx container at startup.

**Session lifetime note for `on_after_register`:** `self.user_db.update()` works correctly only when `UserManager` is obtained through the FastAPI DI chain (`Depends(get_user_manager)`), which provides a `SQLAlchemyUserDatabase` backed by a live async session. Do not instantiate `UserManager` outside the DI chain (e.g., in tests or scripts) and call this hook — the session will be stale or missing. Test the self-registration role-lock specifically in an integration test that confirms the DB row has `role="reader"` regardless of the submitted value.

### 2.2 Docker Network Segmentation

**File:** `docker-compose.yml`

Define two networks:
- `frontend`: caddy, ui, api
- `backend`: api, chromadb

ChromaDB has no `frontend` network entry — UI cannot reach it. Caddy has no `backend` network entry.

Same pattern applied to `docker-compose.test.yml`.

### 2.3 Read-Only Containers

**File:** `docker-compose.yml`

| Service | `read_only` | `tmpfs` |
|---|---|---|
| `ui` | `true` | `/tmp`, `/var/cache/nginx`, `/var/run` |
| `caddy` | partial | `/tmp` (data volume stays writable for certs) |
| `api` | `false` | `/tmp` (vault + db volumes must stay writable) |

### 2.4 Remove `extra_hosts` from Prod

**File:** `docker-compose.yml`

Remove the `extra_hosts: host.docker.internal:host-gateway` block. Ollama communication in prod uses Docker service name (`ollama:11434`) if Ollama is containerized, or a fixed IP if not. Document the alternative in `docs/DEPLOYMENT.md`.

`docker-compose.test.yml` retains `extra_hosts` for dev convenience.

### 2.5 Docker Secrets for Sensitive Config

**File:** `docker-compose.yml`

```yaml
secrets:
  secret_key:
    file: ${HOME}/.kms-secrets/secret_key
  mailgun_signing_key:
    file: ${HOME}/.kms-secrets/mailgun_signing_key

services:
  api:
    secrets:
      - secret_key
      - mailgun_signing_key
```

**Note:** Docker Compose does not expand `~` in `file:` paths for secrets. Use `${HOME}` instead — Compose does expand this env var. Do not use `~` or it will fail at `docker compose up` with a file-not-found error.

**File:** `api/config.py`

Add a `_read_secret(name: str, fallback: str) -> str` helper:
```python
def _read_secret(name: str, fallback: str) -> str:
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    return fallback
```
Override `secret_key` and `mailgun_webhook_signing_key` at `Settings` construction time:
```python
settings = Settings(
    secret_key=_read_secret("secret_key", os.environ.get("SECRET_KEY", "changeme")),
    mailgun_webhook_signing_key=_read_secret(
        "mailgun_signing_key", os.environ.get("MAILGUN_WEBHOOK_SIGNING_KEY", "")
    ),
)
```
This ensures `_read_secret()` runs before the Phase 1 `model_validator` fires, so the validator sees the Docker-secrets value rather than the raw env var. Falls back to the env var so the test environment continues to work without Docker secrets configured.

`${HOME}/.kms-secrets/` is documented in `DEPLOYMENT.md` with instructions to create it with `chmod 700` and populate it with `openssl rand -hex 32 > ~/.kms-secrets/secret_key`.

### 2.6 Encrypted Backups with `age`

**File:** `backup.sh`

After creating the tar archive, pipe through `age`:
```bash
age -r "$AGE_PUBLIC_KEY" < backup.tar.gz > backup.tar.gz.age
rm backup.tar.gz
```

**New env var:** `AGE_PUBLIC_KEY` — the admin's age public key. Stored in `.env` (non-sensitive).

The private key lives on the admin's local machine only. Backup files are unreadable without it.

**Key loss warning:** If the private key is lost, all encrypted backups become permanently unreadable. `DEPLOYMENT.md` must include a prominent warning: store the age private key in a password manager or offline backup. Consider printing and storing it physically for a system holding business-confidential data.

**Update prune glob in `backup.sh`:** Any existing prune/rotation logic that matches `*.tar.gz` must be updated to match `*.tar.gz.age` — after the age change, the unencrypted `.tar.gz` files are deleted immediately and only `.tar.gz.age` files remain. A stale glob will silently fail to prune old backups.

`deploy.sh` updated to verify `AGE_PUBLIC_KEY` is set before running backup.

### 2.7 Host Disk Encryption Requirement

**File:** `docs/DEPLOYMENT.md`

New section: "Host Security Requirements" — documents that the host running KMS must have full-disk encryption (LUKS on Linux). Provides a checklist: verify with `lsblk -o NAME,FSTYPE,MOUNTPOINT`, enable at OS install time. This covers Docker volumes which hold the SQLite DB, ChromaDB, and vault files.

### 2.8 JWT → httpOnly Cookie

**File:** `api/auth/users.py`

Replace:
```python
bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")
```
With:
```python
from fastapi_users.authentication import CookieTransport
cookie_transport = CookieTransport(
    cookie_name="kmstoken",
    cookie_max_age=3600,
    cookie_secure=True,       # only sent over HTTPS
    cookie_httponly=True,     # not accessible from JS
    cookie_samesite="strict", # CSRF protection
    cookie_path="/kms/api",
)
```

**File:** `ui/src/api/client.ts`

- Remove all `localStorage.getItem/setItem/removeItem` calls for `token`.
- Remove manual `Authorization: Bearer` header injection — browser sends cookie automatically.
- Add `credentials: "include"` to all fetch calls, including the AI status poll in `NavBar.tsx` (which calls `GET /health/ai` directly every 30s — verify this call also gets `credentials: "include"` after auth-gating in 1.6).
- Add an explicit `logout()` function that calls `DELETE /auth/jwt/logout`. Without this, clicking logout only clears React state — the httpOnly cookie remains valid in the browser for up to 3600 seconds. The UI logout action must call this endpoint to invalidate the cookie server-side.

**File:** `ui/src/` (auth context)

Replace `localStorage` role/email reads with a React context populated from a `GET /users/me` call at app load. Cache in context, not localStorage.

**CSRF:** `SameSite=Strict` is sufficient — no CSRF token needed.

**Note:** `cookie_secure=True` requires HTTPS. The transport object is instantiated at module import time, so it must read from `settings` at that point. Add `cookie_secure: bool = True` to `config.py` `Settings`, set `COOKIE_SECURE=false` in `.env.test`, and construct the transport as:
```python
cookie_transport = CookieTransport(
    cookie_name="kmstoken",
    cookie_max_age=3600,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite="strict",
    cookie_path="/kms/api",
)
```

### 2.9 Password Strength Enforcement

**File:** `api/auth/users.py`

Override `UserManager.validate_password`:
```python
async def validate_password(self, password: str, user=None):
    if len(password) < 12:
        raise InvalidPasswordException("Password must be at least 12 characters")
    if not any(c.isdigit() for c in password):
        raise InvalidPasswordException("Password must contain at least one digit")
    if not any(not c.isalnum() for c in password):
        raise InvalidPasswordException("Password must contain at least one special character")
```

Apply the same check in `admin/router.py` `reset_password` endpoint (currently only checks 8 chars minimum).

---

## Files Changed Summary

### Phase 1
| File | Change type |
|---|---|
| `api/docs_/service.py` | Add path traversal guard |
| `api/auth/users.py` | Block admin self-reg, password strength |
| `api/ingestion/router.py` | Role gate, token dedup, body size cap |
| `api/main.py` | CORS, rate limiting, disable API docs, auth health/summary |
| `api/config.py` | `allowed_origins`, `enable_api_docs`, secret key validation |
| `api/db/models.py` | Add `AuditLog`, `UsedToken` models |
| `api/audit/__init__.py` | New — empty, creates `audit` package |
| `api/audit/service.py` | New — `log_event()` helper |
| `api/admin/router.py` | Add `GET /admin/audit-log` endpoint |
| `api/Dockerfile` | Remove `--reload` |
| `docker-compose.test.yml` | Add `--reload` to test CMD override |
| `caddy/Caddyfile` | TLS hooks, security headers |
| `.env.example` | Secret key instruction |
| `.env.test` | Set valid test secret key, `ENABLE_API_DOCS=true` |
| `ui/src/**` | Eliminate all inline styles/scripts → CSS files |

### Phase 2
| File | Change type |
|---|---|
| `api/Dockerfile` | Non-root user |
| `ui/Dockerfile` | Non-root nginx user |
| `api/auth/users.py` | CookieTransport, password strength |
| `api/config.py` | Docker secrets reader helper, `COOKIE_SECURE` |
| `ui/src/api/client.ts` | Remove localStorage token, add `credentials: include` |
| `ui/src/` (auth context) | Replace localStorage role/email with `/users/me` context |
| `docker-compose.yml` | Network segmentation, read-only containers, Docker secrets, remove extra_hosts |
| `docker-compose.test.yml` | Network segmentation, remove extra_hosts |
| `backup.sh` | `age` encryption |
| `deploy.sh` | Verify `AGE_PUBLIC_KEY` before backup |
| `docs/DEPLOYMENT.md` | Host disk encryption requirement, secrets setup, Ollama alternative |

---

## Dependencies

### New Python packages (`api/requirements.txt`)
- `slowapi` — rate limiting

### New system tools (host, optional)
- `age` — for encrypted backups (`apt install age` on Ubuntu 22+)

### New env vars
| Var | Used in | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | prod `.env` | CORS origin whitelist |
| `ENABLE_API_DOCS` | `.env.test` only | Re-enable Swagger UI |
| `CADDY_TLS_MODE` | prod `.env` | `off` / `internal` / `auto` |
| `CADDY_DOMAIN` | prod `.env` | Hostname for auto TLS |
| `CADDY_EMAIL` | prod `.env` | ACME contact email |
| `AGE_PUBLIC_KEY` | prod `.env` | Backup encryption recipient |
| `COOKIE_SECURE` | `.env.test` | Set `false` for HTTP test env (field: `cookie_secure: bool = True` in `Settings`) |

---

## Non-Goals

- JWT refresh tokens (existing backlog item, out of scope here)
- Rate limiting on non-auth read endpoints
- PostgreSQL migration
- Role-based document visibility (all authenticated users see all docs)
- Mailgun replay deduplication beyond the 15-minute timestamp + token cache
