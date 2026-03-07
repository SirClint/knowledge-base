# AI-Powered Document Ingestion UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the "New Doc" manual form with an AI-powered textarea that determines whether to create or update a document, picks the correct folder, and flags uncertain placements for human review.

**Architecture:** The existing `/ingest` API endpoint and `classify_ingestion_intent()` Ollama call handle the AI logic — we enhance them to pick folders correctly and return a `needs_review` flag. The frontend replaces the form with a textarea; the review queue surfaces AI-flagged docs alongside overdue ones.

**Tech Stack:** FastAPI (Python), SQLAlchemy async, Ollama/llama3.2, React + TypeScript, Playwright E2E

---

### Task 1: Enhance AI classify function to pick folders and return needs_review

**Files:**
- Modify: `api/ai/service.py`
- Test: `api/tests/test_ai.py`

**Context:** `classify_ingestion_intent()` in `api/ai/service.py:38-46` currently passes existing doc paths to Ollama, but the system prompt doesn't mention available folders, so Ollama doesn't know where to place new docs. The ingestion service defaults to `team/processes/` when no path is returned. We need to tell Ollama which folders exist and ask it to flag uncertain placements.

**Step 1: Write the failing tests**

Add to `api/tests/test_ai.py`:

```python
async def test_classify_ingestion_returns_needs_review():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '{"action": "create", "path": "personal/vague-note.md", "title": "Vague Note", "body": "Some content.", "needs_review": true}'}
        ))
        from ai.service import classify_ingestion_intent
        result = await classify_ingestion_intent("something vague", candidate_paths=[])
        assert result["needs_review"] is True
        assert "action" in result
        assert "path" in result


async def test_classify_ingestion_includes_known_folders_in_prompt():
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "create", "path": "team/architecture/design.md", "title": "Design", "body": "Body.", "needs_review": false}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent("architecture doc", candidate_paths=[])
        assert "team/architecture" in captured["payload"]["prompt"] or "team/architecture" in captured["payload"]["system"]
```

**Step 2: Run tests to verify they fail**

```bash
docker compose exec api pytest api/tests/test_ai.py::test_classify_ingestion_returns_needs_review api/tests/test_ai.py::test_classify_ingestion_includes_known_folders_in_prompt -v
```

Expected: FAIL — `test_classify_ingestion_returns_needs_review` fails because `classify_ingestion_intent` doesn't currently return `needs_review`; `test_classify_ingestion_includes_known_folders_in_prompt` fails because the prompt doesn't include folder names.

**Step 3: Implement the changes**

Replace `classify_ingestion_intent` in `api/ai/service.py` (lines 38-46) with:

```python
KNOWN_FOLDERS = ["personal", "team/processes", "team/architecture", "team/projects"]


async def classify_ingestion_intent(message: str, candidate_paths: list[str]) -> dict:
    prompt = (
        f"Message: {message}\n\n"
        f"Existing doc paths:\n" + "\n".join(candidate_paths[:20]) + "\n\n"
        f"Available folders: {', '.join(KNOWN_FOLDERS)}"
    )
    system = (
        "Return JSON: {\"action\": \"create\"|\"update\", \"path\": string|null, "
        "\"title\": string, \"body\": string, \"needs_review\": boolean}. "
        "If updating, pick the most relevant existing path. "
        "If creating, choose the most appropriate folder from the available folders list and construct a slug filename. "
        "Set needs_review to true if you are unsure about the action or folder placement. "
        "Return ONLY valid JSON."
    )
    raw = await _ollama(prompt, system)
    return json.loads(raw)
```

**Step 4: Run tests to verify they pass**

```bash
docker compose exec api pytest api/tests/test_ai.py -v
```

Expected: All tests PASS (including the 2 new ones and the 2 existing ones).

**Step 5: Commit**

```bash
git add api/ai/service.py api/tests/test_ai.py
git commit -m "feat: enhance classify_ingestion_intent with folder selection and needs_review flag"
```

---

### Task 2: Update ingestion service to handle needs_review

**Files:**
- Modify: `api/ingestion/service.py`
- Test: `api/tests/test_ingestion.py`

**Context:** `ingest_message()` in `api/ingestion/service.py` calls `classify_ingestion_intent()` but ignores the new `needs_review` field. It also defaults to `team/processes/` when no path — change the default to `personal/` since that's a safer fallback for unknown content. After creating/updating the doc, set `doc.status = "needs_review"` if flagged. `create_doc` and `update_doc` in `docs_/service.py` both return the `Document` object, so we can set status directly on the returned object.

**Step 1: Write the failing tests**

Add to `api/tests/test_ingestion.py` (after the existing tests):

```python
async def test_ingest_sets_needs_review_status_on_create():
    mock_doc = MagicMock()
    mock_doc.status = "current"

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "personal/vague-note.md",
        "title": "Vague Note",
        "body": "Some content.",
        "needs_review": True,
    })):
        with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
            from ingestion.service import ingest_message
            result = await ingest_message("something vague", session=_mock_session())
            assert result["needs_review"] is True
            assert mock_doc.status == "needs_review"


async def test_ingest_does_not_set_needs_review_when_confident():
    mock_doc = MagicMock()
    mock_doc.status = "current"

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "team/processes/deploy.md",
        "title": "Deploy Process",
        "body": "Steps.",
        "needs_review": False,
    })):
        with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
            from ingestion.service import ingest_message
            result = await ingest_message("Deploy process steps...", session=_mock_session())
            assert result["needs_review"] is False
            assert mock_doc.status == "current"
```

**Step 2: Run tests to verify they fail**

```bash
docker compose exec api pytest api/tests/test_ingestion.py::test_ingest_sets_needs_review_status_on_create api/tests/test_ingestion.py::test_ingest_does_not_set_needs_review_when_confident -v
```

Expected: FAIL — `ingest_message` doesn't yet return `needs_review` or set `doc.status`.

**Step 3: Implement the changes**

Replace the entire `ingest_message` function in `api/ingestion/service.py`:

```python
async def ingest_message(message: str, session: AsyncSession) -> dict:
    # Get existing doc paths for context
    result = await session.execute(select(Document.path))
    paths = [r[0] for r in result.fetchall()]

    intent = await classify_ingestion_intent(message, paths)
    action = intent.get("action", "create")
    path = intent.get("path", "")
    title = intent.get("title", "Untitled")
    body = intent.get("body", message)
    needs_review = intent.get("needs_review", False)

    if action == "update" and path:
        doc = await update_doc(path, {"title": title, "body": body}, session)
        if needs_review and doc:
            doc.status = "needs_review"
            await session.commit()
        return {"action": "update", "path": path, "needs_review": needs_review, "message": f"Updated doc: {title}."}
    else:
        if not path:
            slug = title.lower().replace(" ", "-")[:40]
            path = f"personal/{slug}.md"
        doc = await create_doc(path, title, body, [], "", session)
        if needs_review:
            doc.status = "needs_review"
            await session.commit()
        return {"action": "create", "path": path, "needs_review": needs_review, "message": f"Created doc: {title}."}
```

**Step 4: Run all ingestion tests**

```bash
docker compose exec api pytest api/tests/test_ingestion.py -v
```

Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add api/ingestion/service.py api/tests/test_ingestion.py
git commit -m "feat: ingestion service propagates needs_review flag and sets doc status"
```

---

### Task 3: Review queue surfaces AI-flagged docs

**Files:**
- Modify: `api/scheduler/jobs.py`
- Modify: `api/review/router.py`
- Test: `api/tests/test_review.py`

**Context:** `get_overdue_docs()` in `api/scheduler/jobs.py:12-24` only returns docs that are past their review interval. We need it to also return docs with `status="needs_review"` (set by the staleness checker or, now, by the ingestion service). The router at `api/review/router.py:9-12` returns a list — we add a `reason` field so the UI can distinguish overdue from AI-flagged docs. Marking a doc reviewed (existing endpoint) already sets `status="current"`, so AI-flagged docs disappear from the queue once reviewed.

**Step 1: Write the failing test**

Add to `api/tests/test_review.py`:

```python
async def test_needs_review_docs_included_in_queue(session):
    flagged = Document(
        path="personal/ai-note.md", title="AI Note",
        last_reviewed=None, status="needs_review"
    )
    session.add(flagged)
    await session.commit()
    results = await get_overdue_docs(session)
    paths = [r.path for r in results]
    assert "personal/ai-note.md" in paths


async def test_overdue_docs_not_affected_by_change(session):
    overdue = Document(
        path="team/processes/old.md", title="Old Doc",
        last_reviewed=str(date.today() - timedelta(days=60)),
        review_interval="30d", status="current"
    )
    session.add(overdue)
    await session.commit()
    results = await get_overdue_docs(session)
    paths = [r.path for r in results]
    assert "team/processes/old.md" in paths
```

**Step 2: Run tests to verify they fail**

```bash
docker compose exec api pytest api/tests/test_review.py::test_needs_review_docs_included_in_queue -v
```

Expected: FAIL — `get_overdue_docs` does not currently return `status="needs_review"` docs.

**Step 3: Update `get_overdue_docs` in `api/scheduler/jobs.py`**

Replace the function (lines 12-24):

```python
async def get_overdue_docs(session: AsyncSession) -> list[Document]:
    # Docs overdue by review interval
    result = await session.execute(select(Document).where(Document.last_reviewed.isnot(None)))
    docs = result.scalars().all()
    overdue = []
    seen_ids: set[int] = set()
    for doc in docs:
        try:
            reviewed = date.fromisoformat(doc.last_reviewed)
            interval = _parse_interval(doc.review_interval or "90d")
            if (date.today() - reviewed).days >= interval:
                overdue.append(doc)
                seen_ids.add(doc.id)
        except (ValueError, TypeError):
            pass

    # Docs flagged by AI ingestion or staleness checker
    result2 = await session.execute(select(Document).where(Document.status == "needs_review"))
    for doc in result2.scalars().all():
        if doc.id not in seen_ids:
            overdue.append(doc)

    return overdue
```

**Step 4: Update `api/review/router.py` to include reason field**

Replace the queue endpoint (lines 9-12):

```python
@router.get("/queue")
async def queue(session=Depends(get_session), user=Depends(current_active_user)):
    docs = await get_overdue_docs(session)
    return [
        {
            "id": d.id,
            "path": d.path,
            "title": d.title,
            "last_reviewed": d.last_reviewed,
            "reason": "AI-created, needs review" if d.status == "needs_review" else "Overdue for review",
        }
        for d in docs
    ]
```

**Step 5: Run all review tests**

```bash
docker compose exec api pytest api/tests/test_review.py -v
```

Expected: All 3 tests PASS.

**Step 6: Run the full backend test suite to check for regressions**

```bash
docker compose exec api pytest -v --ignore=api/tests/test_watcher.py
```

Expected: All tests pass (the watcher tests have a pre-existing unrelated failure — ignore them).

**Step 7: Commit**

```bash
git add api/scheduler/jobs.py api/review/router.py api/tests/test_review.py
git commit -m "feat: review queue includes AI-flagged docs with reason field"
```

---

### Task 4: Frontend — DocPage textarea for new docs + client ingest method

**Files:**
- Modify: `ui/src/api/client.ts`
- Modify: `ui/src/pages/DocPage.tsx`

**Context:** `client.ts` needs an `ingest()` method calling `POST /ingest`. `DocPage.tsx` currently for `isNew` shows title input + category dropdown + CodeMirror editor. Replace that entire branch with a `<textarea>` and "Process with AI" button. The existing view/edit flow for existing docs is untouched. After the `ingest()` call resolves, navigate to `/doc/{path}`. Show a "Processing with AI..." disabled state while waiting for Ollama (which can take several seconds).

**Step 1: Add `ingest` to `api/client.ts`**

In `ui/src/api/client.ts`, add after `listDocs`:

```typescript
ingest: (message: string) => request("/ingest", { method: "POST", body: JSON.stringify({ message }) }),
```

**Step 2: Rebuild and verify the API method exists**

```bash
docker compose build ui && docker compose up -d ui
```

No test for this — it will be exercised by the DocPage and E2E tests.

**Step 3: Rewrite the new-doc section of DocPage.tsx**

Full replacement of `ui/src/pages/DocPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import DocViewer from "../components/DocViewer";
import Editor from "../components/Editor";

interface Doc { title: string; body: string; path: string; }

export default function DocPage() {
  const { "*": path } = useParams();
  const navigate = useNavigate();
  const isNew = path === "new";
  const [doc, setDoc] = useState<Doc>({ title: "", body: "", path: "" });
  const [editing, setEditing] = useState(!isNew ? false : false);
  const [error, setError] = useState("");
  // AI ingestion state
  const [ingestText, setIngestText] = useState("");
  const [ingesting, setIngesting] = useState(false);

  useEffect(() => {
    if (!isNew && path) {
      api.getDoc(path).then(setDoc).catch(() => setError("Document not found"));
    }
  }, [path, isNew]);

  async function save() {
    setError("");
    try {
      await api.updateDoc(path!, { title: doc.title, body: doc.body });
      setEditing(false);
    } catch (e: any) {
      if (e.message?.includes("403")) {
        setError("Permission denied. Your account needs the editor or admin role to save documents.");
      } else {
        setError(e.message ?? "Save failed");
      }
    }
  }

  async function ingest() {
    if (!ingestText.trim()) return;
    setIngesting(true);
    setError("");
    try {
      const result = await api.ingest(ingestText);
      navigate(`/doc/${result.path}`);
    } catch (e: any) {
      setError(e.message ?? "Processing failed");
      setIngesting(false);
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!isNew && !editing && <button onClick={() => setEditing(true)}>Edit</button>}
        {!isNew && editing && <button onClick={save}>Save</button>}
        {!isNew && editing && <button onClick={() => setEditing(false)}>Cancel</button>}
        {error && <span style={{ color: "red", marginLeft: 8 }}>{error}</span>}
      </div>

      {isNew ? (
        <div>
          <h2 style={{ marginTop: 0 }}>New Document</h2>
          <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
            Paste or describe your content. AI will determine the title, folder, and whether to create or update an existing document.
          </p>
          <textarea
            value={ingestText}
            onChange={e => setIngestText(e.target.value)}
            placeholder="Paste notes, content, or describe what you want to document..."
            disabled={ingesting}
            style={{
              display: "block", width: "100%", height: 300,
              padding: 8, fontSize: 14, boxSizing: "border-box",
              fontFamily: "monospace", resize: "vertical",
            }}
          />
          <button
            onClick={ingest}
            disabled={ingesting || !ingestText.trim()}
            style={{ marginTop: 8 }}
          >
            {ingesting ? "Processing with AI..." : "Process with AI"}
          </button>
        </div>
      ) : editing ? (
        <>
          <input
            value={doc.title}
            onChange={e => setDoc(d => ({ ...d, title: e.target.value }))}
            placeholder="Title"
            style={{ display: "block", width: "100%", fontSize: 24, marginBottom: 8, padding: 8, boxSizing: "border-box" }}
          />
          <Editor value={doc.body} onChange={body => setDoc(d => ({ ...d, body }))} />
        </>
      ) : (
        <DocViewer title={doc.title} body={doc.body} />
      )}
    </div>
  );
}
```

**Step 4: Rebuild UI**

```bash
docker compose build ui && docker compose up -d ui
```

Navigate to `http://localhost:8080/kms/` → click "+ New Doc" → should see textarea and "Process with AI" button instead of the old form.

**Step 5: Commit**

```bash
git add ui/src/api/client.ts ui/src/pages/DocPage.tsx
git commit -m "feat: replace new doc form with AI ingestion textarea"
```

---

### Task 5: Frontend — ReviewQueue shows reason + update E2E tests

**Files:**
- Modify: `ui/src/components/ReviewQueue.tsx`
- Modify: `ui/src/pages/ReviewPage.tsx`
- Modify: `e2e/tests/documents.spec.ts`

**Context:** The review queue API now returns a `reason` field. The `ReviewQueue` component shows "Last reviewed: never" for AI-flagged docs — replace that with the reason string. The E2E test `"create a new document"` uses the old form (title input + category select) which no longer exists — replace it with two new tests: one that verifies the textarea UI, one that uses Playwright route mocking to test the full AI flow without needing Ollama.

**Step 1: Update ReviewQueue component**

Replace `ui/src/components/ReviewQueue.tsx`:

```tsx
import { Link } from "react-router-dom";
import { api } from "../api/client";

interface Doc { id: number; path: string; title: string; last_reviewed: string; reason?: string; }
interface Props { docs: Doc[]; onMarked: (id: number) => void; }

export default function ReviewQueue({ docs, onMarked }: Props) {
  if (docs.length === 0) return <p>No docs need review.</p>;
  return (
    <ul style={{ listStyle: "none", padding: 0 }}>
      {docs.map(d => (
        <li key={d.id} style={{ borderBottom: "1px solid #eee", padding: "12px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <Link to={`/doc/${d.path}`} style={{ textDecoration: "none" }}>{d.title || d.path}</Link>
            <div style={{ color: "#888", fontSize: 12 }}>
              {d.reason || `Last reviewed: ${d.last_reviewed || "never"}`}
            </div>
          </div>
          <button onClick={() => api.markReviewed(d.id).then(() => onMarked(d.id))}>
            Mark reviewed
          </button>
        </li>
      ))}
    </ul>
  );
}
```

Note: also swapped the `<a href>` tag for a React Router `<Link>` so navigation works correctly within the SPA.

**Step 2: Update ReviewPage interface**

In `ui/src/pages/ReviewPage.tsx`, update the `Doc` interface to include `reason`:

```tsx
interface Doc { id: number; path: string; title: string; last_reviewed: string; reason?: string; }
```

**Step 3: Update E2E tests**

In `e2e/tests/documents.spec.ts`, replace the `"create a new document"` test with two new tests:

```typescript
test("new doc page shows AI ingestion textarea", async ({ page }) => {
    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");
    await expect(page.locator("textarea")).toBeVisible();
    await expect(page.locator("button:has-text('Process with AI')")).toBeVisible();
    // Old form elements should not exist
    await expect(page.locator('input[placeholder="Title"]')).not.toBeVisible();
});

test("submit content to AI creates a document and navigates to it", async ({ page }) => {
    const docPath = `personal/ai-test-${Date.now()}.md`;

    // Intercept the ingest API so test doesn't depend on Ollama
    await page.route("**/kms/api/ingest", async route => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                action: "create",
                path: docPath,
                needs_review: false,
                message: "Created.",
            }),
        });
    });

    // Intercept the doc fetch for the created doc
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ title: "AI Test Doc", body: "Content generated by AI.", path: docPath }),
        });
    });

    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");
    await page.fill("textarea", "Notes about our deployment pipeline.");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(`**/${docPath}`, { timeout: 5000 });
    await expect(page.locator("text=Content generated by AI.")).toBeVisible();
});
```

**Step 4: Rebuild UI and run E2E tests**

```bash
docker compose build ui && docker compose up -d ui
cd e2e && npx playwright test
```

Expected: All tests pass. The 2 new tests replace the old "create a new document" test. Existing tests for search, view, edit, folder navigation, and review queue still pass.

**Step 5: Commit**

```bash
git add ui/src/components/ReviewQueue.tsx ui/src/pages/ReviewPage.tsx e2e/tests/documents.spec.ts
git commit -m "feat: review queue shows AI reason, E2E tests updated for AI ingestion flow"
```

---

## Verification

After all tasks, run the full test suite:

```bash
# Backend
docker compose exec api pytest -v --ignore=api/tests/test_watcher.py

# E2E
cd e2e && npx playwright test
```

All tests should pass. Then manually test:

1. Open `http://localhost:8080/kms/` → click "+ New Doc" → verify textarea appears
2. Paste a few sentences of notes → click "Process with AI" → verify you're redirected to a created doc
3. Open Review Queue → verify AI-flagged docs show "AI-created, needs review" label
4. Mark an AI-flagged doc as reviewed → verify it disappears from the queue
