# Feature Improvements Design

**Date:** 2026-03-07
**Branch:** feature/folder-navigation-sidebar (or new feature branch)

## Overview

Five improvements to the KMS: Ollama startup integration + AI status indicator, manual document creation fallback, test/prod environment separation, data backup, and admin user management.

---

## 1. Startup Script + Desktop Launcher

**Goal:** Launch the entire stack (Ollama + Docker Compose) with one click.

- `start.sh` — starts `ollama serve` in background (pidfile at `/tmp/ollama-kms.pid`), waits for it to be ready, runs `docker compose up -d` (prod) or `docker compose -f docker-compose.test.yml up -d` (test), opens browser
- `stop.sh` — runs `docker compose down`, kills Ollama pid
- `kms.desktop` — Linux `.desktop` file in project root; user copies to `~/Desktop`
- Flags: `./start.sh` = prod, `./start.sh --test` = test environment

---

## 2. AI Health Endpoint + UI Status Indicator

**Goal:** Show real-time Ollama availability in the UI; gate AI features on status.

### API
- `GET /health/ai` — pings `{OLLAMA_URL}/api/tags`, returns `{"ai": "online"}` or `{"ai": "offline"}`. No auth required.

### UI
- Thin nav bar rendered on all private pages (Home, DocPage, ReviewPage) showing a colored dot + label: "AI: Online" (green) / "AI: Offline" (red)
- Polls `/health/ai` every 30 seconds and on window focus
- AI status passed as prop to `DocPage` to gate the AI ingestion tab

---

## 3. Manual Document Creation Fallback

**Goal:** Allow document creation without AI when Ollama is offline.

- "New Document" page gets two tabs: **AI Ingestion** and **Manual**
- AI tab: existing textarea + "Process with AI" button, disabled + grayed when AI offline, tooltip "AI is currently offline"
- Manual tab: title input + folder dropdown
- Folder list served by new `GET /docs/folders` endpoint (returns `KNOWN_FOLDERS` from `ai/service.py`)
- Manual create calls existing `POST /docs`

---

## 4. Test/Production Environment Separation

**Goal:** Two fully isolated stacks on the same machine.

| | Production | Test |
|---|---|---|
| Compose file | `docker-compose.yml` | `docker-compose.test.yml` |
| Port | 8080 | 8081 |
| Vault | `./vault` | `./vault-test` |
| Volumes | `kb_data`, `caddy_data` | `kb_data_test`, `caddy_data_test` |
| Env file | `.env` | `.env.test` |

- `docker-compose.test.yml` created as a full copy with overridden ports, volume names, vault mount, and env file reference
- `./vault-test/` created as empty starting point
- `.env.test` initialized from `.env.example`

---

## 5. Backup Script + Deployment Workflow

**Goal:** Manual backup before any prod change; enforced via deploy script.

### `backup.sh [--env test|prod]`
- Defaults to prod
- Backs up: vault directory, SQLite DB (via `docker run --volumes-from`), ChromaDB data
- Output: `./backups/YYYY-MM-DD-HHMMSS-{env}.tar.gz`
- Retains last 10 backups (oldest deleted)

### `deploy.sh`
Enforces: backup → verify → rebuild → restart prod

1. Run `backup.sh --env prod` — abort if it fails
2. Print backup location, prompt for confirmation
3. `git pull origin main`
4. `docker compose build api ui`
5. `docker compose up -d`

---

## 6. Admin User Management Page

**Goal:** Admins can list, delete, role-change, and reset passwords for any user.

### API — new `admin/router.py`, prefix `/admin`, all behind `require_admin`
- `GET /admin/users` — list all users (id, email, role, is_active)
- `DELETE /admin/users/{id}` — delete account (cannot delete own account)
- `PATCH /admin/users/{id}/role` — set role to reader/editor/admin
- `POST /admin/users/{id}/reset-password` — body: `{"password": "..."}`, admin sets directly

### UI — new `pages/UsersPage.tsx`
- Route `/users`, admin-only (non-admins redirected to `/`)
- Table: email, role dropdown (onChange fires PATCH immediately), Reset Password button (prompts for new password), Delete button (confirms before delete)
- Nav bar shows "Users" link only when `role === "admin"` (role stored in localStorage on login)
- Role stored in localStorage alongside token at login time

---

## Implementation Order

1. Environment separation (docker-compose.test.yml, vault-test, .env.test)
2. Startup scripts + desktop launcher
3. Backup + deploy scripts
4. AI health endpoint + UI nav bar with status indicator
5. Manual doc creation tab
6. Admin user management (API + UI)
