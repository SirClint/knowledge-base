# Knowledge Management System (KMS)

## ⚠ CRITICAL: Development Workflow

**ALL development work targets the TEST environment. NEVER build or restart prod containers directly.**

```
Fix code → build/test against TEST → commit to branch → PR → merge to main → ./deploy.sh
```

| Action | Correct command |
|--------|----------------|
| Build after code change | `make build-ui` or `make build-api` |
| Run backend tests | `make pytest` |
| Run E2E tests | `make e2e` |
| Deploy to production | `./deploy.sh` (only, after merging to main) |

**Never run bare `docker compose build/up` — it targets prod. Use `make` targets or `docker compose -f docker-compose.test.yml --env-file .env.test ...` for all dev work.**

---

## What This Is
Self-hosted knowledge base with AI-powered search, staleness detection, review queue, version history, comments, and email ingestion.
Access at **http://localhost:8080/kms** when running (prod) or **http://localhost:8081/kms** (test).

## Architecture

```
caddy:8080 → /kms/api/* → api:8000 (FastAPI)
           → /kms*      → ui:80   (Nginx/React SPA)
           chromadb (vector DB), ollama (local LLM, optional)
```

## Key File Map

### Backend (api/)
- `main.py` — FastAPI app, lifespan (DB init, vault indexing, scheduler), all routers registered
- `config.py` — Settings via env vars (SECRET_KEY, VAULT_PATH, OLLAMA_URL, DATABASE_URL, CHROMADB_PATH, MAILGUN_WEBHOOK_SIGNING_KEY, INGEST_EMAIL_WHITELIST)
- `auth/users.py` — FastAPI-Users JWT auth, User model, role-based access (reader/editor/admin)
- `db/models.py` — Document, DocVersion, Comment models (SQLAlchemy); no `body` column on Document (only `body_preview`)
- `db/database.py` — Async SQLite engine + session
- `docs_/router.py` — CRUD endpoints, GET reads full body from vault file; GET /docs/folders returns KNOWN_FOLDERS
- `docs_/service.py` — Doc CRUD + vault file writes; update_doc snapshots to DocVersion before save; delete_doc cleans up versions and comments
- `docs_/parser.py` — YAML frontmatter parser
- `versions/router.py` — GET /versions/{path} (list), POST /versions/{path}/restore/{id}
- `comments/router.py` — GET/POST /comments/{path}, DELETE /comments/{id}
- `admin/router.py` — GET/PATCH/POST/DELETE /admin/users/* (require_admin)
- `watcher/watcher.py` — Indexes vault `.md` files on startup (vault-relative paths)
- `search/service.py` — Keyword (SQL LIKE) + semantic (ChromaDB/Ollama embeddings)
- `ai/service.py` — Ollama calls: embeddings, staleness check, auto-tag, ingestion intent
- `review/router.py` — Review queue + mark-reviewed
- `ingestion/router.py` — POST /ingest (authenticated), POST /ingest/email (Mailgun webhook, public)
- `ingestion/service.py` — ingest_message(): AI classify → create or update doc
- `scheduler/jobs.py` — Nightly staleness check (2 AM cron)

### Frontend (ui/src/)
- `App.tsx` — Routes with `/kms` basename, PrivateRoute wraps children in Layout
- `components/Layout.tsx` — Wraps all private pages with NavBar
- `components/NavBar.tsx` — AI status dot (polls /health/ai every 30s), Users link (admin only), logout
- `api/client.ts` — API client, token/role/email stored in localStorage at login
- `pages/Login.tsx`, `Register.tsx` — Auth forms, role selector on register
- `pages/Home.tsx` — Folder sidebar + search + results list
- `pages/DocPage.tsx` — View/edit/create docs; History panel; Comments section; Delete button (admin)
- `pages/ReviewPage.tsx` — Review queue
- `pages/UsersPage.tsx` — Admin user management (list, change role, reset password, delete)
- `components/Editor.tsx` — CodeMirror 6 markdown editor
- `components/DocViewer.tsx` — Rendered markdown via `marked`

### Infrastructure
- `docker-compose.yml` — Prod: 4 services, ports 8080, volumes kb_data/caddy_data
- `docker-compose.test.yml` — Test: same but port 8081, volumes kb_data_test/caddy_data_test, vault-test/
- `caddy/Caddyfile` — HTTP :8080, path-based routing
- `caddy/Caddyfile.test` — HTTP :8081
- `ui/Dockerfile` — Multi-stage: node build → nginx serve
- `api/Dockerfile` — Python 3.12-slim, uvicorn with --reload
- `.env` / `.env.example` — Prod runtime config
- `.env.test` — Test runtime config (tracked in git, placeholder values only)

### Scripts
- `start.sh [--test]` — Start Ollama + Docker stack + open browser (prod or test)
- `stop.sh [--test]` — Stop stack + Ollama (prod stops Ollama, test does not)
- `backup.sh [--env prod|test]` — Archive vault + SQLite + ChromaDB to backups/
- `deploy.sh` — Backup prod → confirm → git pull main → rebuild → restart prod
- `deploy-test.sh` — Backup test → confirm → git pull current branch → rebuild → restart test
- `kms.desktop`, `kms-test.desktop` — Linux desktop launchers (copy to ~/Desktop)

### Tests
- `api/tests/` — pytest (asyncio_mode=auto), 51 tests; run: `docker compose exec api pytest -v`
- `e2e/` — Playwright, 24 tests; run: `cd e2e && npx playwright test`
- E2E covers: auth, doc CRUD, search, review queue, admin users, version history, comments, smoke (AI online check)
- Integration tests: `api/tests/test_health_integration.py` — run from host, not inside Docker

### Docs
- `docs/DEPLOYMENT.md` — Environments, workflow, deploy process, backup/restore, reset procedure
- `docs/plans/` — Design docs and implementation plans for each feature batch

## Dev Commands

```bash
# Start/stop
./start.sh --test             # Start test environment  ← use this for development
./stop.sh --test              # Stop test environment
./start.sh                    # Start prod (only after deploy.sh)
./stop.sh                     # Stop prod

# Deploy (prod only, after merging to main)
./backup.sh --env prod        # Manual backup (ALWAYS run before destructive actions)
./deploy-test.sh              # Deploy current branch to test (practice run)
./deploy.sh                   # Deploy main to prod (includes auto-backup)

# Development — all targets operate on TEST environment
make build-ui                 # Rebuild UI after frontend changes
make build-api                # Rebuild API after backend changes
make build                    # Rebuild all services
make pytest                   # Run backend tests (test env)
make e2e                      # Run E2E tests (test env)
make logs-api                 # Tail API logs (test env)

# Raw test-env docker commands (if not using make)
docker compose -f docker-compose.test.yml --env-file .env.test build ui
docker compose -f docker-compose.test.yml --env-file .env.test up -d ui
docker compose -f docker-compose.test.yml --env-file .env.test exec api pytest -v
docker compose -f docker-compose.test.yml --env-file .env.test logs api --tail 30
```

## Known Issues & Gotchas

- **No `body` column in DB** — full doc body is read from vault file at request time
- **Watcher must store vault-relative paths** — e.g. `personal/doc.md` not `/vault/personal/doc.md`
- **Ollama is optional** — app starts without it; embedding calls have 5s timeout and are wrapped in try/except
- **API startup blocks on vault indexing** — each file attempts Ollama embedding (5s timeout × file count); wait for /health before running E2E after restart
- **Docker build caching** — use `--no-cache` only when changing dependencies (package.json/requirements.txt)
- **API source not volume-mounted** — must `docker compose build api` after backend changes for tests to see new code
- **SPA routing** — Caddy strips `/kms` prefix; Vite `base: '/kms/'`; React Router `basename="/kms"`
- **Role self-assignment** — registration endpoint doesn't restrict role selection (anyone can register as admin)
- **JWT lifetime** — 1 hour, no refresh tokens
- **UI uses inline styles** — no CSS framework
- **Ollama UFW rule** — one-time setup: `sudo ufw allow from 172.18.0.0/16 to any port 11434`. Subnet-based so it survives Docker network recreates permanently.
- **`body_preview` not updated on save** — DB preview field only set at create time; stale after edits
- **Mailgun requires public URL** — email ingestion only works if host is reachable from internet (use ngrok for local testing)

## Non-Functional Improvement Areas

- [ ] Restrict admin role self-registration (require existing admin invite)
- [ ] Add JWT refresh tokens
- [ ] Add proper CSS/design system
- [ ] Add loading states and spinners throughout UI
- [ ] PostgreSQL option for production
- [ ] HTTPS/TLS support (Caddy `tls internal` was removed for local dev)
- [ ] File watcher for live vault changes (currently only indexes on startup)
- [ ] Pagination on search results
- [ ] Tag management UI
- [ ] CI/CD pipeline (run E2E tests on PR)
- [ ] Rate limiting on auth + ingest endpoints
- [ ] Proper logging throughout API
- [ ] Role gate on `POST /ingest` — currently any authenticated user (including `reader`) can create/update docs via ingestion; should require `editor`/`admin`
- [ ] Path traversal guard in `docs_/service.py` — vault path is not validated to stay within `VAULT_PATH` before file writes
- [ ] Add `json.JSONDecodeError` handling to `suggest_tags` and `check_staleness` in `ai/service.py`
- [x] ~~Permanent UFW rule for Ollama~~ — fixed: subnet-based rule `sudo ufw allow from 172.18.0.0/16 to any port 11434`
- [ ] `body_preview` should update on doc save, not just create
- [ ] Smoke E2E test should skip gracefully when Ollama is offline (not fail hard)
- [ ] Mailgun replay token deduplication (currently only 15-minute timestamp window)
- [ ] `/health/summary` review queue count uses `get_overdue_docs()` (fetches all docs into memory); replace with a COUNT SQL query as doc count grows

# currentDate
Today's date is 2026-03-09.
