# Knowledge Management System (KMS)

## What This Is
Self-hosted knowledge base with AI-powered search, staleness detection, and review queue.
Access at **http://localhost:8080/kms** when running.

## Architecture

```
caddy:8080 → /kms/api/* → api:8000 (FastAPI)
           → /kms*      → ui:80   (Nginx/React SPA)
           chromadb (vector DB), ollama (local LLM, optional)
```

## Key File Map

### Backend (api/)
- `main.py` — FastAPI app, lifespan (DB init, vault indexing, scheduler)
- `config.py` — Settings via env vars
- `auth/users.py` — FastAPI-Users JWT auth, User model, role-based access (reader/editor/admin)
- `db/models.py` — Document model (SQLAlchemy), no `body` column (only `body_preview`)
- `db/database.py` — Async SQLite engine + session
- `docs_/router.py` — CRUD endpoints, GET reads full body from vault file
- `docs_/service.py` — Doc CRUD + vault file writes
- `docs_/parser.py` — YAML frontmatter parser
- `watcher/watcher.py` — Indexes vault `.md` files on startup (vault-relative paths)
- `search/service.py` — Keyword (SQL LIKE) + semantic (ChromaDB/Ollama embeddings)
- `ai/service.py` — Ollama calls: embeddings, staleness check, auto-tag, ingestion intent
- `review/router.py` — Review queue + mark-reviewed
- `scheduler/jobs.py` — Nightly staleness check (2 AM cron)
- `ingestion/` — AI-powered unstructured text → doc creation/update

### Frontend (ui/src/)
- `App.tsx` — Routes with `/kms` basename, PrivateRoute via localStorage token
- `api/client.ts` — API client, token injection, default search mode: keyword
- `pages/Login.tsx`, `Register.tsx` — Auth forms, role selector on register
- `pages/Home.tsx` — Search bar + results list (React Router `<Link>`)
- `pages/DocPage.tsx` — View/edit/create docs, category dropdown, error handling
- `pages/ReviewPage.tsx` — Review queue
- `components/Editor.tsx` — CodeMirror 6 markdown editor
- `components/DocViewer.tsx` — Rendered markdown via `marked`

### Infrastructure
- `docker-compose.yml` — 4 services (api, ui, chromadb, caddy), 2 volumes (kb_data, caddy_data)
- `caddy/Caddyfile` — HTTP on :8080, path-based routing
- `ui/Dockerfile` — Multi-stage: node build → nginx serve
- `api/Dockerfile` — Python 3.12-slim, uvicorn with --reload
- `.env` / `.env.example` — Runtime config

### Tests
- `api/tests/` — pytest (asyncio_mode=auto), run: `docker compose exec api pytest -v`
- `e2e/` — Playwright, 11 tests, run: `cd e2e && npx playwright test`
- E2E covers: register, login, logout, auth redirect, doc CRUD, search, review queue

### Docs
- `docs/plans/2026-02-24-knowledge-management-design.md` — Original design
- `docs/plans/2026-03-01-knowledge-management-system.md` — Implementation spec
- `docs/plans/2026-03-02-playwright-e2e-tests.md` — E2E test plan

## Dev Commands

```bash
docker compose up -d                      # Start stack
docker compose build api ui && docker compose up -d  # Rebuild after code changes
docker compose down                       # Stop
docker compose down -v                    # Stop + wipe data
docker compose logs api --tail 30         # Debug API
docker compose exec api pytest -v         # Backend tests
cd e2e && npx playwright test             # E2E tests
```

## Known Issues & Gotchas

- **No `body` column in DB** — full doc body is read from vault file at request time
- **Watcher must store vault-relative paths** — e.g. `personal/doc.md` not `/vault/personal/doc.md`
- **Ollama is optional** — app starts without it; embedding calls have 5s timeout and are wrapped in try/except
- **API startup blocks on vault indexing** — each file attempts Ollama embedding (5s timeout × file count)
- **Docker build caching** — use `--no-cache` only when changing dependencies (package.json/requirements.txt)
- **SPA routing** — Caddy strips `/kms` prefix; Vite `base: '/kms/'`; React Router `basename="/kms"`
- **Role self-assignment** — registration endpoint doesn't restrict role selection (anyone can register as admin)
- **JWT lifetime** — 1 hour, no refresh tokens
- **UI uses inline styles** — no CSS framework

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
- [ ] User management UI (admin panel)
- [ ] CI/CD pipeline (run E2E tests on PR)
- [ ] Rate limiting on auth endpoints
- [ ] Proper logging throughout API
