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

**File:** `api/docs_/service.py`

Add a `_safe_path(path: str) -> Path` helper that:
1. Resolves `Path(settings.vault_path) / path` to an absolute path
2. Asserts the resolved path starts with `Path(settings.vault_path).resolve()`
3. Raises `HTTP 400` if not

Call this at the top of `write_doc_file`, `get_doc`, `update_doc`, and `delete_doc` before any file I/O. Rejects paths containing `..` or any traversal that escapes the vault root.

### 1.2 Block Admin Self-Registration

**File:** `api/auth/users.py`

Override `UserManager.on_after_register` to forcibly set `user.role = "reader"` regardless of submitted value, then commit. The `UserCreate` schema retains the `role` field for admin panel use. Public registration always produces a `reader`. Role promotion goes through `PATCH /admin/users/{id}/role` only.

### 1.3 Role Gate on `POST /ingest`

**File:** `api/ingestion/router.py`

Change dependency from `current_active_user` to `require_editor`. Reader-role users receive HTTP 403.

### 1.4 Rate Limiting

**New dependency:** `slowapi`

**File:** `api/main.py` + individual route files

Apply via `slowapi` limiter:

| Endpoint | Limit |
|---|---|
| `POST /auth/jwt/login` | 10/minute per IP |
| `POST /auth/register` | 5/minute per IP |
| `POST /ingest` | 30/minute per user |
| `POST /ingest/email` | 20/minute per IP |

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

### 1.6 Protect API Docs and Health Summary

**File:** `api/main.py`

- Change `FastAPI(docs_url=...)` to `docs_url="/api-docs" if settings.enable_api_docs else None` and same for `redoc_url`.
- Add `enable_api_docs: bool = False` to `config.py`.
- Set `ENABLE_API_DOCS=true` in `.env.test` only.
- Add `Depends(current_active_user)` to `GET /health/summary`.

### 1.7 Email Ingestion Hardening

#### Token Deduplication

**New DB model:** `UsedToken(token: str PK, used_at: DateTime)`

**File:** `api/ingestion/router.py`

Before processing an email webhook:
1. Check if `token` exists in `UsedToken`. If yes → HTTP 403 "Duplicate request".
2. Insert `UsedToken(token=token, used_at=now())`.
3. Prune entries older than 24 hours on each request (async, fire-and-forget).

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
| `auth.login_failure` | `UserManager.on_failed_login` (fastapi-users hook) |
| `doc.create` | `docs_/router.py` POST |
| `doc.update` | `docs_/router.py` PUT |
| `doc.delete` | `docs_/router.py` DELETE |
| `user.role_change` | `admin/router.py` PATCH role |
| `user.delete` | `admin/router.py` DELETE |
| `user.password_reset` | `admin/router.py` POST reset-password |
| `ingest.email` | `ingestion/router.py` POST /email (log sender + subject only, not body) |

**New endpoint:** `GET /admin/audit-log?page=1&limit=50` — admin-only, returns paginated `AuditLog` rows newest-first.

### 1.9 TLS Config Hooks in Caddy

**New env var:** `CADDY_TLS_MODE` — values: `off` (default), `internal`, `auto`
**New env var:** `CADDY_DOMAIN` — hostname for `auto` mode

**File:** `caddy/Caddyfile`

```
{$CADDY_DOMAIN:localhost}:{$CADDY_PORT:8080} {
    # TLS block injected per CADDY_TLS_MODE:
    # auto:     tls {$CADDY_EMAIL}
    # internal: tls internal
    # off:      (no tls block)

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'"
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

After `settings = Settings()`, add:
```python
if settings.secret_key in ("changeme", "") or len(settings.secret_key) < 32:
    raise RuntimeError(
        "SECRET_KEY is insecure. Generate one with: openssl rand -hex 32"
    )
```

**File:** `.env.example`

```
SECRET_KEY=<generate with: openssl rand -hex 32>
```

**File:** `.env.test`

Set a valid 32-char test key (placeholder, tracked in git — acceptable for test env).

### 1.12 UI Inline Style/Script Elimination

**Scope:** All files under `ui/src/`

Audit every component for:
- `style={{...}}` props → extract to `.css` class
- Inline `<script>` tags → none expected, but verify
- `dangerouslySetInnerHTML` → audit for XSS risk

Extract styles into `ui/src/styles/` directory with one CSS file per component or a shared `global.css`. This is a **prerequisite** for deploying the `Content-Security-Policy` header — the header is added to the Caddyfile only after the UI sweep is confirmed clean.

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
    file: ~/.kms-secrets/secret_key
  mailgun_signing_key:
    file: ~/.kms-secrets/mailgun_signing_key

services:
  api:
    secrets:
      - secret_key
      - mailgun_signing_key
```

**File:** `api/config.py`

Add a helper that reads from `/run/secrets/<name>` if the file exists, otherwise falls back to the env var. This keeps test env working without Docker secrets.

`~/.kms-secrets/` is documented in `DEPLOYMENT.md` with instructions to create it with `chmod 700` and populate it with `openssl rand -hex 32 > ~/.kms-secrets/secret_key`.

### 2.6 Encrypted Backups with `age`

**File:** `backup.sh`

After creating the tar archive, pipe through `age`:
```bash
age -r "$AGE_PUBLIC_KEY" < backup.tar.gz > backup.tar.gz.age
rm backup.tar.gz
```

**New env var:** `AGE_PUBLIC_KEY` — the admin's age public key. Stored in `.env` (non-sensitive).

The private key lives on the admin's local machine only. Backup files are unreadable without it.

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
- Add `credentials: "include"` to all fetch calls.

**File:** `ui/src/` (auth context)

Replace `localStorage` role/email reads with a React context populated from a `GET /users/me` call at app load. Cache in context, not localStorage.

**CSRF:** `SameSite=Strict` is sufficient — no CSRF token needed.

**Note:** `cookie_secure=True` requires HTTPS. In test env (HTTP), set `cookie_secure=False` via `COOKIE_SECURE=false` env var.

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
| `COOKIE_SECURE` | `.env.test` | Set `false` for HTTP test env |

---

## Non-Goals

- JWT refresh tokens (existing backlog item, out of scope here)
- Rate limiting on non-auth read endpoints
- PostgreSQL migration
- Role-based document visibility (all authenticated users see all docs)
- Mailgun replay deduplication beyond the 15-minute timestamp + token cache
