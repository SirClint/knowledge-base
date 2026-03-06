# Folder Navigation Sidebar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a collapsible folder tree sidebar to the Home page so users can click a folder to browse its documents without searching.

**Architecture:** Add a `GET /docs` list endpoint to the API. On page load, the frontend fetches all docs and derives the folder tree from their paths. Clicking a folder filters the in-memory doc list and displays results — no extra API call. Searching clears the active folder; clicking a folder clears the search.

**Tech Stack:** FastAPI (Python), React + TypeScript, inline styles (no CSS framework), pytest + httpx for backend tests, Playwright for E2E.

---

### Task 1: Add `GET /docs` list endpoint

**Files:**
- Modify: `api/docs_/router.py`
- Test: `api/tests/test_docs.py`

**Step 1: Write the failing test**

Append to `api/tests/test_docs.py`:

```python
async def test_list_docs(editor_client):
    # Create two docs in different folders
    await editor_client.post("/docs", json={
        "title": "Personal Note",
        "path": "personal/note.md",
        "body": "content",
        "tags": [],
        "owner": "ed@test.com",
    })
    await editor_client.post("/docs", json={
        "title": "Deploy Process",
        "path": "team/processes/deploy.md",
        "body": "steps",
        "tags": [],
        "owner": "ed@test.com",
    })
    r = await editor_client.get("/docs")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    paths = [d["path"] for d in data]
    assert "personal/note.md" in paths
    assert "team/processes/deploy.md" in paths
    for d in data:
        assert "id" in d
        assert "path" in d
        assert "title" in d
```

**Step 2: Run test to verify it fails**

```bash
docker compose exec api pytest tests/test_docs.py::test_list_docs -v
```

Expected: FAIL with 404 or 405 (route not found).

**Step 3: Implement `GET /docs`**

In `api/docs_/router.py`, add this route **before** the `GET /{path:path}` route (order matters — FastAPI matches top-to-bottom):

```python
@router.get("", dependencies=[Depends(current_active_user)])
async def list_all(session=Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(Document))
    docs = result.scalars().all()
    return [{"id": d.id, "path": d.path, "title": d.title} for d in docs]
```

Also add the missing import at the top of the file:

```python
from db.models import Document
```

**Step 4: Run test to verify it passes**

```bash
docker compose exec api pytest tests/test_docs.py::test_list_docs -v
```

Expected: PASS.

**Step 5: Run the full test suite to check for regressions**

```bash
docker compose exec api pytest -v
```

Expected: All tests pass.

**Step 6: Commit**

```bash
git add api/docs_/router.py api/tests/test_docs.py
git commit -m "feat: add GET /docs list endpoint"
```

---

### Task 2: Add `listDocs()` to the frontend API client

**Files:**
- Modify: `ui/src/api/client.ts`

**Step 1: Add the method**

In `ui/src/api/client.ts`, add `listDocs` to the `api` object (after `search`):

```typescript
listDocs: () => request("/docs"),
```

**Step 2: Commit**

```bash
git add ui/src/api/client.ts
git commit -m "feat: add listDocs API client method"
```

---

### Task 3: Refactor Home.tsx with two-column layout and folder sidebar

**Files:**
- Modify: `ui/src/pages/Home.tsx`

**Step 1: Replace the entire file content**

```tsx
import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import SearchBar from "../components/SearchBar";

interface DocResult { id: number; path: string; title: string; }

/** Derive a nested folder tree from flat doc paths.
 *  e.g. ["personal/a.md", "team/processes/b.md"]
 *  → { personal: {}, team: { processes: {} } }
 */
function buildFolderTree(docs: DocResult[]): Record<string, Record<string, object>> {
  const tree: Record<string, Record<string, object>> = {};
  for (const doc of docs) {
    const parts = doc.path.split("/");
    if (parts.length < 2) continue; // no folder
    const [top, ...rest] = parts;
    if (!tree[top]) tree[top] = {};
    if (rest.length >= 2) {
      const sub = rest[0];
      if (!tree[top][sub]) (tree[top] as Record<string, object>)[sub] = {};
    }
  }
  return tree;
}

export default function Home() {
  const [allDocs, setAllDocs] = useState<DocResult[]>([]);
  const [results, setResults] = useState<DocResult[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.listDocs().then((docs: DocResult[]) => setAllDocs(docs));
  }, []);

  const folderTree = buildFolderTree(allDocs);

  function handleFolderClick(folderPath: string) {
    setActiveFolder(folderPath);
    setSearchQuery("");
    const filtered = allDocs.filter(d => d.path.startsWith(folderPath + "/"));
    setResults(filtered);
  }

  function toggleExpand(folder: string) {
    setExpanded(prev => ({ ...prev, [folder]: !prev[folder] }));
  }

  async function handleSearch(q: string) {
    if (!q.trim()) return;
    setActiveFolder(null);
    const data = await api.search(q);
    setResults(data);
  }

  const activeFolderStyle = { fontWeight: "bold" as const, color: "#0055cc" };
  const folderStyle = { cursor: "pointer", padding: "4px 0", userSelect: "none" as const };

  return (
    <div style={{ maxWidth: 1100, margin: "40px auto", padding: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Knowledge Base</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => navigate("/doc/new")}>+ New Doc</button>
          <button onClick={() => navigate("/review")}>Review Queue</button>
          <button onClick={() => { localStorage.removeItem("token"); navigate("/login"); }}>Log out</button>
        </div>
      </div>

      {/* Two-column layout */}
      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* Sidebar */}
        <div style={{ width: 220, flexShrink: 0, borderRight: "1px solid #ddd", paddingRight: 16 }}>
          <div style={{ fontSize: 12, fontWeight: "bold", color: "#888", marginBottom: 8, textTransform: "uppercase" }}>
            Folders
          </div>
          {Object.keys(folderTree).sort().map(top => {
            const subFolders = Object.keys(folderTree[top]).sort();
            const isTopActive = activeFolder === top;
            const isExpanded = expanded[top];
            return (
              <div key={top}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  {subFolders.length > 0 && (
                    <span
                      style={{ fontSize: 10, cursor: "pointer", width: 12 }}
                      onClick={() => toggleExpand(top)}
                    >
                      {isExpanded ? "▼" : "▶"}
                    </span>
                  )}
                  {subFolders.length === 0 && <span style={{ width: 12 }} />}
                  <span
                    style={{ ...folderStyle, ...(isTopActive ? activeFolderStyle : {}) }}
                    onClick={() => handleFolderClick(top)}
                  >
                    {top}
                  </span>
                </div>
                {isExpanded && subFolders.map(sub => {
                  const subPath = `${top}/${sub}`;
                  const isSubActive = activeFolder === subPath;
                  return (
                    <div
                      key={sub}
                      style={{ ...folderStyle, paddingLeft: 24, ...(isSubActive ? activeFolderStyle : {}) }}
                      onClick={() => handleFolderClick(subPath)}
                    >
                      {sub}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Main content */}
        <div style={{ flex: 1 }}>
          <SearchBar onSearch={handleSearch} searchQuery={searchQuery} onQueryChange={setSearchQuery} />
          {activeFolder && (
            <div style={{ color: "#888", fontSize: 13, marginBottom: 8 }}>
              Browsing: <strong>{activeFolder}</strong>
              <span
                style={{ marginLeft: 8, cursor: "pointer", color: "#cc0000" }}
                onClick={() => { setActiveFolder(null); setResults([]); }}
              >
                ✕
              </span>
            </div>
          )}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {results.map(r => (
              <li key={r.id} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
                <Link to={`/doc/${r.path}`} style={{ textDecoration: "none" }}>{r.title || r.path}</Link>
                <span style={{ color: "#888", fontSize: 12, marginLeft: 8 }}>{r.path}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update SearchBar to accept controlled query prop (if needed)**

Check `ui/src/components/SearchBar.tsx`. If it manages its own input state internally (not accepting a `searchQuery` prop), you have two options:
- **Option A (simpler):** Remove the `searchQuery` and `onQueryChange` props from the `Home.tsx` call above and just pass `onSearch`. Accept that typing a search doesn't visually clear the folder highlight until the user submits.
- **Option B:** Update `SearchBar` to accept optional `value` and `onChange` props to make it controlled.

Read the file first: if `SearchBar` already accepts a `value` prop, use Option B. Otherwise use Option A and remove `searchQuery` and `onQueryChange` from the `<SearchBar>` call in `Home.tsx`.

**Step 3: Rebuild and restart**

```bash
docker compose build ui && docker compose up -d ui
```

**Step 4: Manual smoke test**

1. Open http://localhost:8080/kms
2. Confirm left sidebar shows folder names (personal, team)
3. Click `team` — confirm it expands to show `processes`, `architecture`, `projects`
4. Click `processes` — confirm results show only `team/processes/` docs
5. Click `personal` — confirm results show only `personal/` docs
6. Type a search query — confirm folder highlight clears, search results appear

**Step 5: Commit**

```bash
git add ui/src/pages/Home.tsx ui/src/components/SearchBar.tsx
git commit -m "feat: add folder navigation sidebar to home page"
```

---

### Task 4: Add E2E test for folder navigation

**Files:**
- Modify: `e2e/tests/documents.spec.ts`

**Step 1: Write the failing test**

Append inside the `test.describe("Documents", ...)` block:

```typescript
test("click folder to browse documents", async ({ page }) => {
  // Create a doc in team/processes
  const title = `Process Doc ${Date.now()}`;
  const path = `team/processes/${title.toLowerCase().replace(/\s+/g, "-")}.md`;
  await page.request.post("http://localhost:8080/kms/api/docs", {
    headers: { Authorization: `Bearer ${await getToken(page)}` },
    data: { title, path, body: "Process content", tags: [] },
  });

  // Create a doc in personal (to confirm it's NOT shown)
  const otherTitle = `Personal Note ${Date.now()}`;
  await page.request.post("http://localhost:8080/kms/api/docs", {
    headers: { Authorization: `Bearer ${await getToken(page)}` },
    data: {
      title: otherTitle,
      path: `personal/${otherTitle.toLowerCase().replace(/\s+/g, "-")}.md`,
      body: "Personal content",
      tags: [],
    },
  });

  await page.goto("./");

  // Expand team folder
  await page.click("text=▶", { timeout: 5000 });

  // Click processes subfolder
  await page.click("text=processes");

  // The team/processes doc should appear
  await expect(page.locator(`text=${title}`)).toBeVisible();

  // The personal doc should NOT appear
  await expect(page.locator(`text=${otherTitle}`)).not.toBeVisible();
});
```

**Step 2: Run the E2E tests**

```bash
cd e2e && npx playwright test --reporter=line
```

Expected: All tests pass including the new folder navigation test.

**Step 3: Commit**

```bash
git add e2e/tests/documents.spec.ts
git commit -m "test: add E2E test for folder navigation sidebar"
```
