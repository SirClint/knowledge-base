# Feature Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Ollama startup integration + AI status indicator, manual doc creation fallback, test/prod environment separation, backup/deploy scripts, and admin user management to the KMS.

**Architecture:** Scripts handle orchestration (start/stop/backup/deploy) at the shell level. API gains `/health/ai` and `/admin/*` endpoints. UI gains a shared NavBar (with AI status + admin link), a two-tab new-doc page, and an admin Users page. Environments are fully separated by compose file, volumes, vault directory, and `.env` file.

**Tech Stack:** Bash scripts, Docker Compose, FastAPI + FastAPI-Users (SQLAlchemy), React (TypeScript), Playwright E2E, pytest (asyncio)

---

## Task 1: Environment Separation — Compose + Vault + Env

**Files:**
- Create: `docker-compose.test.yml`
- Create: `vault-test/.gitkeep`
- Create: `.env.test`

**Step 1: Create the test compose file**

Copy `docker-compose.yml` entirely, then make these four changes:
- Caddy `ports`: `"8081:8081"`
- Caddy `Caddyfile` volume: add a second Caddyfile for test (see step 2)
- All volume names: `kb_data` → `kb_data_test`, `caddy_data` → `caddy_data_test`
- API vault mount: `./vault:/vault` → `./vault-test:/vault`
- Add `env_file: .env.test` to the api service (replacing or alongside the default)

Full `docker-compose.test.yml`:

```yaml
services:
  api:
    build: ./api
    volumes:
      - ./vault-test:/vault
      - kb_data_test:/data
    env_file: .env.test
    depends_on:
      - chromadb
    extra_hosts:
      - "host.docker.internal:host-gateway"

  ui:
    build: ./ui

  chromadb:
    image: chromadb/chroma:latest
    volumes:
      - kb_data_test:/chroma/chroma

  caddy:
    image: caddy:2-alpine
    ports:
      - "8081:8081"
    volumes:
      - ./caddy/Caddyfile.test:/etc/caddy/Caddyfile
      - caddy_data_test:/data

volumes:
  kb_data_test:
  caddy_data_test:
```

**Step 2: Create the test Caddyfile**

Create `caddy/Caddyfile.test` — copy `caddy/Caddyfile` exactly, then change the port from `8080` to `8081`.

Read `caddy/Caddyfile` first to get the exact content, then create `caddy/Caddyfile.test` with port `8081`.

**Step 3: Create vault-test directory and .env.test**

```bash
mkdir -p vault-test
touch vault-test/.gitkeep
cp .env.example .env.test
```

**.env.test contents** (same as .env.example — user fills in their secret key):
```
SECRET_KEY=changeme-test
VAULT_PATH=/vault
OLLAMA_URL=http://host.docker.internal:11434
DATABASE_URL=sqlite+aiosqlite:////data/kb.db
CHROMADB_PATH=/data/chroma
```

**Step 4: Add vault-test to .gitignore (keep test data out of git)**

Append to `.gitignore`:
```
vault-test/
!vault-test/.gitkeep
```

**Step 5: Verify both compose files parse correctly**

```bash
docker compose config --quiet
docker compose -f docker-compose.test.yml config --quiet
```
Expected: no errors, no output

**Step 6: Commit**

```bash
git add docker-compose.test.yml caddy/Caddyfile.test vault-test/.gitkeep .env.test .gitignore
git commit -m "feat: add test environment (port 8081, isolated volumes and vault)"
```

---

## Task 2: Startup and Stop Scripts + Desktop Launcher

**Files:**
- Create: `start.sh`
- Create: `stop.sh`
- Create: `kms.desktop`

**Step 1: Write start.sh**

```bash
#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--test" ]]; then
  ENV="test"
fi

COMPOSE_FILE="docker-compose.yml"
PORT=8080
if [[ "$ENV" == "test" ]]; then
  COMPOSE_FILE="docker-compose.test.yml"
  PORT=8081
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OLLAMA_PID_FILE="/tmp/ollama-kms.pid"

# Start Ollama if not already running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
  echo "Starting Ollama..."
  ollama serve &>/tmp/ollama-kms.log &
  echo $! > "$OLLAMA_PID_FILE"
  # Wait up to 10 seconds for Ollama to be ready
  for i in $(seq 1 10); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
      echo "Ollama is ready."
      break
    fi
    sleep 1
  done
else
  echo "Ollama is already running."
fi

# Start Docker stack
echo "Starting KMS ($ENV) on port $PORT..."
docker compose -f "$COMPOSE_FILE" up -d

# Open browser (try common Linux methods, then macOS)
URL="http://localhost:$PORT/kms"
echo "Opening $URL"
if command -v xdg-open &>/dev/null; then
  xdg-open "$URL" &
elif command -v open &>/dev/null; then
  open "$URL"
fi

echo "KMS ($ENV) started at $URL"
```

**Step 2: Write stop.sh**

```bash
#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--test" ]]; then
  ENV="test"
fi

COMPOSE_FILE="docker-compose.yml"
if [[ "$ENV" == "test" ]]; then
  COMPOSE_FILE="docker-compose.test.yml"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping KMS ($ENV)..."
docker compose -f "$COMPOSE_FILE" down

# Only kill Ollama if stopping prod (don't kill if test is still running)
if [[ "$ENV" == "prod" ]]; then
  OLLAMA_PID_FILE="/tmp/ollama-kms.pid"
  if [[ -f "$OLLAMA_PID_FILE" ]]; then
    PID=$(cat "$OLLAMA_PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      echo "Stopping Ollama (pid $PID)..."
      kill "$PID"
    fi
    rm -f "$OLLAMA_PID_FILE"
  fi
fi

echo "KMS ($ENV) stopped."
```

**Step 3: Make scripts executable**

```bash
chmod +x start.sh stop.sh
```

**Step 4: Write kms.desktop**

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=Knowledge Base (Prod)
Comment=Start the KMS production environment
Exec=bash -c "cd /home/clinterrific/AI/knowledge-base && ./start.sh"
Icon=utilities-terminal
Terminal=true
Categories=Utility;
```

Also create `kms-test.desktop`:
```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=Knowledge Base (Test)
Comment=Start the KMS test environment
Exec=bash -c "cd /home/clinterrific/AI/knowledge-base && ./start.sh --test"
Icon=utilities-terminal
Terminal=true
Categories=Utility;
```

**Step 5: Manual test — run start.sh and verify**

```bash
./start.sh
```
Expected: Ollama starts (or "already running"), docker containers come up, browser opens at http://localhost:8080/kms

**Step 6: Commit**

```bash
git add start.sh stop.sh kms.desktop kms-test.desktop
git commit -m "feat: startup/stop scripts and desktop launchers for prod and test"
```

---

## Task 3: Backup Script + Deploy Script

**Files:**
- Create: `backup.sh`
- Create: `deploy.sh`
- Create: `backups/.gitkeep`

**Step 1: Write backup.sh**

```bash
#!/usr/bin/env bash
set -e

ENV="prod"
if [[ "$1" == "--env" && -n "$2" ]]; then
  ENV="$2"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +%Y-%m-%d-%H%M%S)
BACKUP_NAME="${TIMESTAMP}-${ENV}"
BACKUP_DIR="$SCRIPT_DIR/backups"
STAGING_DIR="/tmp/kms-backup-${BACKUP_NAME}"

mkdir -p "$BACKUP_DIR" "$STAGING_DIR"

# Determine vault source
if [[ "$ENV" == "prod" ]]; then
  VAULT_SRC="$SCRIPT_DIR/vault"
  COMPOSE_FILE="docker-compose.yml"
  VOLUME_NAME="knowledge-base_kb_data"
else
  VAULT_SRC="$SCRIPT_DIR/vault-test"
  COMPOSE_FILE="docker-compose.test.yml"
  VOLUME_NAME="knowledge-base_kb_data_test"
fi

echo "Backing up KMS ($ENV) to backups/${BACKUP_NAME}.tar.gz ..."

# 1. Copy vault files
cp -r "$VAULT_SRC" "$STAGING_DIR/vault"

# 2. Dump SQLite DB from Docker volume
docker run --rm \
  -v "${VOLUME_NAME}:/data:ro" \
  -v "${STAGING_DIR}:/backup" \
  busybox \
  cp /data/kb.db /backup/kb.db

# 3. Dump ChromaDB from Docker volume
docker run --rm \
  -v "${VOLUME_NAME}:/data:ro" \
  -v "${STAGING_DIR}:/backup" \
  busybox \
  sh -c "cp -r /data/chroma /backup/chroma 2>/dev/null || true"

# 4. Create archive
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C /tmp "kms-backup-${BACKUP_NAME}"
rm -rf "$STAGING_DIR"

echo "Backup saved: backups/${BACKUP_NAME}.tar.gz"

# 5. Keep only last 10 backups
ls -t "${BACKUP_DIR}"/*.tar.gz 2>/dev/null | tail -n +11 | xargs -r rm -f
echo "Done."
```

**Step 2: Write deploy.sh**

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  KMS Production Deployment"
echo "======================================"
echo ""
echo "Step 1/4: Backing up production data..."
./backup.sh --env prod
echo ""
echo "Step 2/4: Backup complete."
read -r -p "Continue with deployment? (yes/no): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Deployment aborted."
  exit 1
fi

echo ""
echo "Step 3/4: Pulling latest code from main..."
git pull origin main

echo ""
echo "Step 4/4: Rebuilding and restarting production stack..."
docker compose build api ui
docker compose up -d

echo ""
echo "Deployment complete. KMS prod running at http://localhost:8080/kms"
```

**Step 3: Make scripts executable and create backups dir**

```bash
chmod +x backup.sh deploy.sh
mkdir -p backups
touch backups/.gitkeep
```

**Step 4: Add backups to .gitignore**

Append to `.gitignore`:
```
backups/*.tar.gz
```

**Step 5: Test backup.sh against prod**

```bash
./backup.sh --env prod
ls backups/
```
Expected: a `.tar.gz` file with today's timestamp and `-prod` suffix.

**Step 6: Commit**

```bash
git add backup.sh deploy.sh backups/.gitkeep .gitignore
git commit -m "feat: manual backup script and guarded deploy script (backup-before-deploy enforced)"
```

---

## Task 4: AI Health API Endpoint

**Files:**
- Modify: `api/main.py`
- Create: `api/tests/test_health.py`

**Step 1: Write the failing test**

Create `api/tests/test_health.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_ai_online(client):
    mock_response = AsyncMock()
    mock_response.status_code = 200
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        r = await client.get("/health/ai")
    assert r.status_code == 200
    assert r.json() == {"ai": "online"}


async def test_health_ai_offline(client):
    import httpx
    with patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("connection refused")):
        r = await client.get("/health/ai")
    assert r.status_code == 200
    assert r.json() == {"ai": "offline"}
```

**Step 2: Run to verify it fails**

```bash
docker compose exec api pytest api/tests/test_health.py -v
```
Expected: FAIL — `test_health_ai_online` fails because `/health/ai` doesn't exist (404)

**Step 3: Implement the endpoint in main.py**

Add after the existing `/health` endpoint in `api/main.py`:

```python
@app.get("/health/ai")
async def health_ai():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            if r.status_code == 200:
                return {"ai": "online"}
    except Exception:
        pass
    return {"ai": "offline"}
```

**Step 4: Run tests to verify they pass**

```bash
docker compose exec api pytest api/tests/test_health.py -v
```
Expected: PASS (both tests)

**Step 5: Rebuild and smoke test manually**

```bash
docker compose build api && docker compose up -d api
curl http://localhost:8080/kms/api/health/ai
```
Expected: `{"ai":"online"}` or `{"ai":"offline"}` depending on Ollama state

**Step 6: Commit**

```bash
git add api/main.py api/tests/test_health.py
git commit -m "feat: GET /health/ai endpoint — reports Ollama online/offline status"
```

---

## Task 5: UI NavBar with AI Status + Role Stored at Login

**Files:**
- Create: `ui/src/components/NavBar.tsx`
- Create: `ui/src/components/Layout.tsx`
- Modify: `ui/src/api/client.ts`
- Modify: `ui/src/App.tsx`
- Modify: `ui/src/pages/Home.tsx` (remove duplicate nav buttons)

**Step 1: Add role storage to login in client.ts**

The login function currently only returns the token. After login, we need to fetch `/users/me` to get the role and store it. Update `api/client.ts`:

Replace the `login` function with:

```typescript
login: async (email: string, password: string) => {
  const r = await fetch(`${BASE}/auth/jwt/login`, {
    method: "POST",
    body: new URLSearchParams({ username: email, password }),
  });
  const data = await r.json();
  if (data.access_token) {
    localStorage.setItem("token", data.access_token);
    // Fetch role and store it
    const me = await fetch(`${BASE}/users/me`, {
      headers: { Authorization: `Bearer ${data.access_token}` },
    }).then(r => r.json());
    localStorage.setItem("role", me.role ?? "reader");
  }
  return data;
},
```

Also add a `getMe` method at the end of the api object:
```typescript
getMe: () => request("/users/me"),
```

**Step 2: Update Login.tsx to use new login**

Read `ui/src/pages/Login.tsx` first, then check if it currently calls `localStorage.setItem("token", ...)` itself — if so, remove that line since `api.login` now handles it. The navigate call after login should remain.

**Step 3: Create NavBar.tsx**

Create `ui/src/components/NavBar.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";

export default function NavBar() {
  const [aiStatus, setAiStatus] = useState<"online" | "offline" | "checking">("checking");
  const navigate = useNavigate();
  const role = localStorage.getItem("role");
  const BASE = import.meta.env.VITE_API_URL ?? "/kms/api";

  async function checkAi() {
    try {
      const r = await fetch(`${BASE}/health/ai`);
      const data = await r.json();
      setAiStatus(data.ai === "online" ? "online" : "offline");
    } catch {
      setAiStatus("offline");
    }
  }

  useEffect(() => {
    checkAi();
    const interval = setInterval(checkAi, 30000);
    const onFocus = () => checkAi();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    navigate("/login");
  }

  const dotColor = aiStatus === "online" ? "#22c55e" : aiStatus === "offline" ? "#ef4444" : "#999";
  const dotLabel = aiStatus === "checking" ? "AI: checking..." : `AI: ${aiStatus}`;

  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "8px 24px", background: "#f8f8f8", borderBottom: "1px solid #ddd",
      fontSize: 13,
    }}>
      <Link to="/" style={{ fontWeight: "bold", textDecoration: "none", color: "#333" }}>
        Knowledge Base
      </Link>
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <span>
          <span style={{
            display: "inline-block", width: 8, height: 8, borderRadius: "50%",
            background: dotColor, marginRight: 5,
          }} />
          {dotLabel}
        </span>
        {role === "admin" && (
          <Link to="/users" style={{ textDecoration: "none", color: "#555" }}>Users</Link>
        )}
        <button onClick={logout} style={{ fontSize: 12, padding: "2px 8px" }}>Log out</button>
      </div>
    </div>
  );
}
```

**Step 4: Create Layout.tsx**

Create `ui/src/components/Layout.tsx`:

```tsx
import NavBar from "./NavBar";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <NavBar />
      {children}
    </div>
  );
}
```

**Step 5: Update App.tsx to use Layout**

Replace `PrivateRoute` in `App.tsx` so it wraps children in `Layout`:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import DocPage from "./pages/DocPage";
import ReviewPage from "./pages/ReviewPage";
import Layout from "./components/Layout";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return localStorage.getItem("token")
    ? <Layout>{children}</Layout>
    : <Navigate to="/login" />;
}

export default function App() {
  return (
    <BrowserRouter basename="/kms">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/" element={<PrivateRoute><Home /></PrivateRoute>} />
        <Route path="/doc/*" element={<PrivateRoute><DocPage /></PrivateRoute>} />
        <Route path="/review" element={<PrivateRoute><ReviewPage /></PrivateRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
```

**Step 6: Clean up Home.tsx — remove duplicate logout button**

In `Home.tsx`, the header currently has `+ New Doc`, `Review Queue`, and `Log out` buttons. Remove only the `Log out` button (NavBar now handles it). Keep `+ New Doc` and `Review Queue` in the page header — they are page-specific actions, not global nav.

**Step 7: Rebuild UI and verify manually**

```bash
docker compose build ui && docker compose up -d ui
```

Navigate to http://localhost:8080/kms — verify:
- NavBar appears at top with AI status dot
- Dot is green if Ollama is running, red if not
- "Users" link only visible when logged in as admin role

**Step 8: Commit**

```bash
git add ui/src/components/NavBar.tsx ui/src/components/Layout.tsx ui/src/App.tsx ui/src/api/client.ts ui/src/pages/Home.tsx ui/src/pages/Login.tsx
git commit -m "feat: NavBar with AI status indicator, role stored at login"
```

---

## Task 6: Folders Endpoint + Manual Doc Creation Tab

**Files:**
- Modify: `api/docs_/router.py`
- Create: `api/tests/test_folders.py`
- Modify: `ui/src/pages/DocPage.tsx`

**Step 1: Write failing test for folders endpoint**

Create `api/tests/test_folders.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def auth_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/register", json={"email": "u@test.com", "password": "pass", "role": "reader"})
        r = await c.post("/auth/jwt/login", data={"username": "u@test.com", "password": "pass"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_get_folders(auth_client):
    r = await auth_client.get("/docs/folders")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert "personal" in data
    assert "team/processes" in data
```

**Step 2: Run test to verify it fails**

```bash
docker compose exec api pytest api/tests/test_folders.py -v
```
Expected: FAIL — 404 (endpoint doesn't exist)

**Step 3: Add the folders endpoint to docs_/router.py**

Read `api/docs_/router.py` first to find the right place. Then add this endpoint (before or after the existing list endpoint):

```python
from ai.service import KNOWN_FOLDERS

@router.get("/docs/folders")
async def list_folders(user=Depends(current_active_user)):
    return KNOWN_FOLDERS
```

**Step 4: Run test to verify it passes**

```bash
docker compose exec api pytest api/tests/test_folders.py -v
```
Expected: PASS

**Step 5: Update DocPage.tsx — add two-tab interface**

Replace the `isNew` block in `DocPage.tsx` with a two-tab layout. Key changes:

- Add state: `const [tab, setTab] = useState<"ai" | "manual">("ai")`
- Add state: `const [folders, setFolders] = useState<string[]>([])`
- Add state: `const [manualTitle, setManualTitle] = useState("")`
- Add state: `const [manualFolder, setManualFolder] = useState("")`
- Add state: `const [aiOnline, setAiOnline] = useState<boolean | null>(null)`
- On mount (when `isNew`), fetch `/health/ai` and `/docs/folders`

Add `useEffect` for the new page:
```tsx
useEffect(() => {
  if (!isNew) return;
  const BASE = import.meta.env.VITE_API_URL ?? "/kms/api";
  fetch(`${BASE}/health/ai`).then(r => r.json()).then(d => setAiOnline(d.ai === "online"));
  api.getFolders().then(setFolders);
}, [isNew]);
```

Add `getFolders` to `api/client.ts`:
```typescript
getFolders: () => request("/docs/folders"),
```

Add `manualCreate` function to `DocPage.tsx`:
```tsx
async function manualCreate() {
  if (!manualTitle.trim() || !manualFolder) return;
  setError("");
  const slug = manualTitle.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const path = `${manualFolder}/${slug}.md`;
  try {
    await api.createDoc({ title: manualTitle.trim(), body: "", path, tags: [] });
    navigate(`/doc/${path}`);
  } catch (e: any) {
    setError(e.message ?? "Create failed");
  }
}
```

Replace the `isNew` JSX with:

```tsx
{isNew ? (
  <div>
    <h2 style={{ marginTop: 0 }}>New Document</h2>
    {/* Tab bar */}
    <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "1px solid #ddd" }}>
      <button
        onClick={() => setTab("ai")}
        style={{
          padding: "6px 16px", border: "none", borderBottom: tab === "ai" ? "2px solid #333" : "2px solid transparent",
          background: "none", cursor: "pointer", fontWeight: tab === "ai" ? "bold" : "normal",
        }}
      >
        AI Ingestion
      </button>
      <button
        onClick={() => setTab("manual")}
        style={{
          padding: "6px 16px", border: "none", borderBottom: tab === "manual" ? "2px solid #333" : "2px solid transparent",
          background: "none", cursor: "pointer", fontWeight: tab === "manual" ? "bold" : "normal",
        }}
      >
        Manual
      </button>
    </div>

    {tab === "ai" ? (
      <div>
        <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
          Paste or describe your content. AI will determine the title, folder, and whether to create or update an existing document.
        </p>
        {aiOnline === false && (
          <div style={{ color: "#b45309", background: "#fef3c7", padding: "8px 12px", borderRadius: 4, marginBottom: 12, fontSize: 13 }}>
            AI is currently offline. Use the Manual tab to create a document without AI.
          </div>
        )}
        <textarea
          value={ingestText}
          onChange={e => setIngestText(e.target.value)}
          placeholder="Paste notes, content, or describe what you want to document..."
          disabled={ingesting || aiOnline === false}
          style={{
            display: "block", width: "100%", height: 300,
            padding: 8, fontSize: 14, boxSizing: "border-box",
            fontFamily: "monospace", resize: "vertical",
            opacity: aiOnline === false ? 0.5 : 1,
          }}
        />
        {error && <div style={{ color: "red", marginTop: 8 }}>{error}</div>}
        <button
          onClick={ingest}
          disabled={ingesting || !ingestText.trim() || aiOnline === false}
          title={aiOnline === false ? "AI is currently offline" : undefined}
          style={{ marginTop: 8, opacity: aiOnline === false ? 0.5 : 1, cursor: aiOnline === false ? "not-allowed" : "pointer" }}
        >
          {ingesting ? "Processing with AI..." : "Process with AI"}
        </button>
      </div>
    ) : (
      <div>
        <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
          Enter a title and choose a folder. The document will be created empty and ready to edit.
        </p>
        <input
          value={manualTitle}
          onChange={e => setManualTitle(e.target.value)}
          placeholder="Document title"
          style={{ display: "block", width: "100%", fontSize: 18, marginBottom: 12, padding: 8, boxSizing: "border-box" }}
        />
        <select
          value={manualFolder}
          onChange={e => setManualFolder(e.target.value)}
          style={{ display: "block", width: "100%", padding: 8, fontSize: 14, marginBottom: 12, boxSizing: "border-box" }}
        >
          <option value="">— Select a folder —</option>
          {folders.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
        <button
          onClick={manualCreate}
          disabled={!manualTitle.trim() || !manualFolder}
        >
          Create Document
        </button>
      </div>
    )}
  </div>
) : editing ? (
```

**Step 6: Rebuild and verify manually**

```bash
docker compose build api ui && docker compose up -d
```

Go to http://localhost:8080/kms/doc/new:
- Both tabs visible
- Manual tab: title input + folder dropdown, Create button
- AI tab: if Ollama offline → warning message + disabled textarea + disabled button

**Step 7: Commit**

```bash
git add api/docs_/router.py api/tests/test_folders.py ui/src/pages/DocPage.tsx ui/src/api/client.ts
git commit -m "feat: manual doc creation tab on new-doc page, GET /docs/folders endpoint"
```

---

## Task 7: Admin User Management API

**Files:**
- Create: `api/admin/__init__.py`
- Create: `api/admin/router.py`
- Create: `api/tests/test_admin.py`
- Modify: `api/main.py`

**Step 1: Write failing tests**

Create `api/tests/test_admin.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


async def _make_client_with_role(role: str):
    """Helper: returns (client, token) for a registered user with given role."""
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    email = f"{role}@test.com"
    await c.post("/auth/register", json={"email": email, "password": "pass", "role": role})
    r = await c.post("/auth/jwt/login", data={"username": email, "password": "pass"})
    token = r.json()["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c


@pytest.fixture
async def admin_client():
    c = await _make_client_with_role("admin")
    yield c
    await c.aclose()


@pytest.fixture
async def reader_client():
    c = await _make_client_with_role("reader")
    yield c
    await c.aclose()


async def test_list_users_as_admin(admin_client):
    r = await admin_client.get("/admin/users")
    assert r.status_code == 200
    users = r.json()
    assert isinstance(users, list)
    assert any(u["email"] == "admin@test.com" for u in users)


async def test_list_users_forbidden_for_reader(reader_client):
    r = await reader_client.get("/admin/users")
    assert r.status_code == 403


async def test_change_role(admin_client):
    # Register a target user
    await admin_client.post("/auth/register", json={"email": "target@test.com", "password": "pass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "target@test.com")
    r = await admin_client.patch(f"/admin/users/{target['id']}/role", json={"role": "editor"})
    assert r.status_code == 200
    assert r.json()["role"] == "editor"


async def test_reset_password(admin_client):
    await admin_client.post("/auth/register", json={"email": "reset@test.com", "password": "oldpass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "reset@test.com")
    r = await admin_client.post(f"/admin/users/{target['id']}/reset-password", json={"password": "newpass123"})
    assert r.status_code == 200
    # Verify new password works
    login = await admin_client.post("/auth/jwt/login", data={"username": "reset@test.com", "password": "newpass123"})
    assert "access_token" in login.json()


async def test_delete_user(admin_client):
    await admin_client.post("/auth/register", json={"email": "todelete@test.com", "password": "pass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "todelete@test.com")
    r = await admin_client.delete(f"/admin/users/{target['id']}")
    assert r.status_code == 204
    users_after = (await admin_client.get("/admin/users")).json()
    assert not any(u["email"] == "todelete@test.com" for u in users_after)


async def test_cannot_delete_own_account(admin_client):
    users = (await admin_client.get("/admin/users")).json()
    self_user = next(u for u in users if u["email"] == "admin@test.com")
    r = await admin_client.delete(f"/admin/users/{self_user['id']}")
    assert r.status_code == 400
```

**Step 2: Run tests to verify they fail**

```bash
docker compose exec api pytest api/tests/test_admin.py -v
```
Expected: FAIL — 404 on all `/admin/*` routes

**Step 3: Create the admin router**

Create `api/admin/__init__.py` (empty).

Create `api/admin/router.py`:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from db.database import get_session
from auth.users import User, require_admin, current_active_user, get_user_manager

router = APIRouter(prefix="/admin", tags=["admin"])


class RoleUpdate(BaseModel):
    role: str


class PasswordReset(BaseModel):
    password: str


@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [
        {"id": str(u.id), "email": u.email, "role": u.role, "is_active": u.is_active}
        for u in users
    ]


@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    if body.role not in ("reader", "editor", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = body.role
    await session.commit()
    await session.refresh(user)
    return {"id": str(user.id), "email": user.email, "role": user.role, "is_active": user.is_active}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: uuid.UUID,
    body: PasswordReset,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
    user_manager=Depends(get_user_manager),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user.hashed_password = user_manager.password_helper.hash(body.password)
    await session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(require_admin),
):
    if current.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
```

**Step 4: Register the admin router in main.py**

Add after the ingestion router import/include block:

```python
# ── Admin routes ──────────────────────────────────────────────────────────────
from admin.router import router as admin_router

app.include_router(admin_router)
```

**Step 5: Run tests to verify they pass**

```bash
docker compose exec api pytest api/tests/test_admin.py -v
```
Expected: all 5 tests PASS

**Step 6: Run full test suite to check for regressions**

```bash
docker compose exec api pytest -v
```
Expected: all existing tests still pass

**Step 7: Commit**

```bash
git add api/admin/__init__.py api/admin/router.py api/tests/test_admin.py api/main.py
git commit -m "feat: admin API — list users, change role, reset password, delete user"
```

---

## Task 8: Admin User Management UI Page

**Files:**
- Create: `ui/src/pages/UsersPage.tsx`
- Modify: `ui/src/api/client.ts`
- Modify: `ui/src/App.tsx`

**Step 1: Add admin API methods to client.ts**

Add to the `api` object in `client.ts`:

```typescript
listUsers: () => request("/admin/users"),
changeRole: (id: string, role: string) => request(`/admin/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
resetPassword: (id: string, password: string) => request(`/admin/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ password }) }),
deleteUser: (id: string) => request(`/admin/users/${id}`, { method: "DELETE" }),
```

**Step 2: Create UsersPage.tsx**

Create `ui/src/pages/UsersPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

interface User { id: string; email: string; role: string; is_active: boolean; }

const ROLES = ["reader", "editor", "admin"];

export default function UsersPage() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Guard: non-admin should not reach this page
  useEffect(() => {
    if (localStorage.getItem("role") !== "admin") {
      navigate("/");
      return;
    }
    load();
  }, []);

  async function load() {
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch {
      setError("Failed to load users");
    }
  }

  async function changeRole(id: string, role: string) {
    setError(""); setMessage("");
    try {
      await api.changeRole(id, role);
      setMessage("Role updated.");
      load();
    } catch (e: any) {
      setError(e.message ?? "Failed to update role");
    }
  }

  async function resetPassword(id: string, email: string) {
    const pw = window.prompt(`Set new password for ${email} (min 8 chars):`);
    if (!pw) return;
    setError(""); setMessage("");
    try {
      await api.resetPassword(id, pw);
      setMessage(`Password reset for ${email}.`);
    } catch (e: any) {
      setError(e.message ?? "Failed to reset password");
    }
  }

  async function deleteUser(id: string, email: string) {
    if (!window.confirm(`Delete account for ${email}? This cannot be undone.`)) return;
    setError(""); setMessage("");
    try {
      await api.deleteUser(id);
      setMessage(`Deleted ${email}.`);
      load();
    } catch (e: any) {
      setError(e.message ?? "Failed to delete user");
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <h2 style={{ marginTop: 0 }}>User Management</h2>
      {error && <div style={{ color: "red", marginBottom: 12 }}>{error}</div>}
      {message && <div style={{ color: "green", marginBottom: 12 }}>{message}</div>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
            <th style={{ padding: "8px 12px" }}>Email</th>
            <th style={{ padding: "8px 12px" }}>Role</th>
            <th style={{ padding: "8px 12px" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "8px 12px" }}>{u.email}</td>
              <td style={{ padding: "8px 12px" }}>
                <select
                  value={u.role}
                  onChange={e => changeRole(u.id, e.target.value)}
                  style={{ fontSize: 13 }}
                >
                  {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </td>
              <td style={{ padding: "8px 12px", display: "flex", gap: 8 }}>
                <button onClick={() => resetPassword(u.id, u.email)} style={{ fontSize: 12 }}>
                  Reset Password
                </button>
                <button
                  onClick={() => deleteUser(u.id, u.email)}
                  style={{ fontSize: 12, color: "white", background: "#dc2626", border: "none", padding: "3px 8px", cursor: "pointer" }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

**Step 3: Add route to App.tsx**

Import `UsersPage` and add a route:

```tsx
import UsersPage from "./pages/UsersPage";
```

Add inside `<Routes>`:
```tsx
<Route path="/users" element={<PrivateRoute><UsersPage /></PrivateRoute>} />
```

**Step 4: Rebuild and verify manually**

```bash
docker compose build ui && docker compose up -d ui
```

Log in as admin — verify:
- NavBar shows "Users" link
- `/kms/users` shows user table with role dropdowns and action buttons
- Changing a role saves immediately
- Reset Password prompts and updates
- Delete asks for confirmation and removes the row

Log in as non-admin — verify:
- NavBar has no "Users" link
- Navigating to `/kms/users` redirects to `/`

**Step 5: Commit**

```bash
git add ui/src/pages/UsersPage.tsx ui/src/App.tsx ui/src/api/client.ts
git commit -m "feat: admin user management page — list, change role, reset password, delete"
```

---

## Task 9: E2E Test for Admin User Management

**Files:**
- Create: `e2e/tests/admin-users.spec.ts`

**Step 1: Write E2E tests**

Create `e2e/tests/admin-users.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test("admin can see Users link in nav", async ({ page }) => {
  await registerAndLogin(page, { role: "admin" });
  await expect(page.locator("text=Users")).toBeVisible();
});

test("reader cannot see Users link in nav", async ({ page }) => {
  await registerAndLogin(page, { role: "reader" });
  await expect(page.locator("text=Users")).not.toBeVisible();
});

test("admin can list users and change role", async ({ page }) => {
  await registerAndLogin(page, { role: "admin" });

  // Create a target user via API
  const targetEmail = uniqueEmail();
  await page.request.post("http://localhost:8080/kms/api/auth/register", {
    data: { email: targetEmail, password: "testpassword123", role: "reader" },
  });

  await page.goto("./users");
  await expect(page.locator(`text=${targetEmail}`)).toBeVisible();

  // Change role from reader to editor
  const row = page.locator(`tr:has-text("${targetEmail}")`);
  await row.locator("select").selectOption("editor");

  // Verify the change persisted (reload)
  await page.reload();
  await expect(row.locator("select")).toHaveValue("editor");
});

test("admin can delete a user", async ({ page }) => {
  await registerAndLogin(page, { role: "admin" });

  const targetEmail = uniqueEmail();
  await page.request.post("http://localhost:8080/kms/api/auth/register", {
    data: { email: targetEmail, password: "testpassword123", role: "reader" },
  });

  await page.goto("./users");
  await expect(page.locator(`text=${targetEmail}`)).toBeVisible();

  page.on("dialog", d => d.accept());
  const row = page.locator(`tr:has-text("${targetEmail}")`);
  await row.locator("button:has-text('Delete')").click();
  await expect(page.locator(`text=${targetEmail}`)).not.toBeVisible();
});

test("non-admin redirected away from /users", async ({ page }) => {
  await registerAndLogin(page, { role: "reader" });
  await page.goto("./users");
  await expect(page).toHaveURL(/\/kms\/?$/);
});
```

**Step 2: Run E2E tests**

```bash
cd e2e && npx playwright test admin-users.spec.ts
```
Expected: all 4 tests pass

**Step 3: Run full E2E suite to check for regressions**

```bash
cd e2e && npx playwright test
```
Expected: all tests pass (11 existing + 4 new = 15 total)

**Step 4: Commit**

```bash
git add e2e/tests/admin-users.spec.ts
git commit -m "test: E2E tests for admin user management page"
```

---

## Final Verification

After all tasks complete:

```bash
# All backend tests
docker compose exec api pytest -v

# All E2E tests
cd e2e && npx playwright test
```

Both suites should pass with no failures.

---

## Summary of New Files

| File | Purpose |
|---|---|
| `docker-compose.test.yml` | Test environment (port 8081) |
| `caddy/Caddyfile.test` | Caddy config for test port |
| `.env.test` | Test environment variables |
| `vault-test/.gitkeep` | Test vault directory |
| `start.sh` | Launch Ollama + Docker stack |
| `stop.sh` | Shutdown stack + Ollama |
| `kms.desktop` | Desktop launcher (prod) |
| `kms-test.desktop` | Desktop launcher (test) |
| `backup.sh` | Manual backup script |
| `deploy.sh` | Guarded deploy (backup → pull → rebuild) |
| `backups/.gitkeep` | Backup output directory |
| `api/admin/__init__.py` | Admin module |
| `api/admin/router.py` | Admin user management endpoints |
| `api/tests/test_health.py` | AI health endpoint tests |
| `api/tests/test_folders.py` | Folders endpoint test |
| `api/tests/test_admin.py` | Admin API tests |
| `ui/src/components/NavBar.tsx` | Global nav with AI status |
| `ui/src/components/Layout.tsx` | Layout wrapper for private routes |
| `ui/src/pages/UsersPage.tsx` | Admin user management page |
| `e2e/tests/admin-users.spec.ts` | E2E tests for admin page |
