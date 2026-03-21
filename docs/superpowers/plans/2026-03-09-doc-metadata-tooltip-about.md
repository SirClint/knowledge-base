# Document Metadata, Review Queue Tooltip, and About Help Section — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add document authorship/edit metadata to every doc page, a hover tooltip on the Review Queue button, and an expanded About modal with feature list and vault user guide.

**Architecture:** Backend gains two new SQLite columns (`created_at`, `updated_by`) on the `Document` model with a startup ALTER TABLE migration (no Alembic). The GET /docs/{path} response is extended with four metadata fields. The frontend renders a metadata bar below the doc title in view mode and expands the About modal. All three features get automated tests (pytest + Playwright E2E).

**Tech Stack:** Python/FastAPI, SQLAlchemy async + SQLite, React 18/TypeScript, Playwright, pytest-asyncio. Docker-based test env (port 8081). All `make` targets operate on the TEST environment.

---

## Build cycle reference

After any change to `api/`, you must rebuild and restart:
```bash
make build-api
docker compose -f docker-compose.test.yml --env-file .env.test up -d api
```

After any change to `ui/`:
```bash
make build-ui
docker compose -f docker-compose.test.yml --env-file .env.test up -d ui
```

Verify the api is healthy before running tests (startup blocks on vault indexing):
```bash
docker compose -f docker-compose.test.yml --env-file .env.test logs api --tail 20
```

---

## Task 1: Create feature branch

- [ ] **Step 1: Create and switch to a feature branch**

```bash
git checkout -b feature/doc-metadata-tooltip-about
```

---

## Task 2: Write failing backend tests (TDD red phase)

**Files:**
- Modify: `api/tests/test_docs.py`

- [ ] **Step 1: Add two new test functions to the bottom of `api/tests/test_docs.py`**

```python
async def test_doc_get_includes_metadata(editor_client):
    await editor_client.post("/docs", json={
        "title": "Meta Test Doc",
        "path": "personal/meta-create-test.md",
        "body": "some body",
        "tags": [],
        "owner": "ed@test.com",
    })
    r = await editor_client.get("/docs/personal/meta-create-test.md")
    assert r.status_code == 200
    data = r.json()
    assert data["created_at"] is not None, "created_at should be set on creation"
    assert data["created_by"] == "ed@test.com", "created_by should equal owner"
    assert data["updated_at"] is not None, "updated_at should be present"
    assert not data["updated_by"], "updated_by should be empty on fresh create"


async def test_doc_update_sets_updated_by(editor_client):
    await editor_client.post("/docs", json={
        "title": "Update Meta Doc",
        "path": "personal/meta-update-test.md",
        "body": "original",
        "tags": [],
        "owner": "ed@test.com",
    })
    await editor_client.put("/docs/personal/meta-update-test.md", json={"title": "Updated Title"})
    r = await editor_client.get("/docs/personal/meta-update-test.md")
    assert r.status_code == 200
    data = r.json()
    assert data["updated_by"] == "ed@test.com", "updated_by should equal editor email after save"
```

- [ ] **Step 2: Build API and run the new tests — expect them to FAIL**

```bash
make build-api
docker compose -f docker-compose.test.yml --env-file .env.test up -d api
make pytest
```

Expected: `FAILED test_doc_get_includes_metadata` and `FAILED test_doc_update_sets_updated_by` — `KeyError: 'created_at'` or similar. The existing 5 tests should still pass.

---

## Task 3: Add model columns (TDD green phase — backend)

**Files:**
- Modify: `api/db/models.py`

- [ ] **Step 1: Add `created_at` and `updated_by` columns to the `Document` class in `api/db/models.py`**

Add these two lines after the existing `indexed_at` column (line 22):

```python
created_at = Column(DateTime, nullable=True)
updated_by = Column(String, default="")
```

The full `Document` class column block should look like:
```python
id = Column(Integer, primary_key=True)
path = Column(String, unique=True, nullable=False, index=True)
title = Column(String, default="")
tags = Column(String, default="[]")
owner = Column(String, default="")
status = Column(String, default="current")
created = Column(String, nullable=True)
last_reviewed = Column(String, nullable=True)
review_interval = Column(String, default="90d")
body_preview = Column(String, default="")
indexed_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
created_at = Column(DateTime, nullable=True)
updated_by = Column(String, default="")
```

---

## Task 4: Add migration to database.py

**Files:**
- Modify: `api/db/database.py`

- [ ] **Step 1: Add ALTER TABLE migration immediately after `create_all` in `create_db()`**

The current `create_db()` function (lines 28–30):

```python
async def create_db():
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

Replace with:

```python
async def create_db():
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        for stmt in [
            "ALTER TABLE documents ADD COLUMN created_at DATETIME",
            "ALTER TABLE documents ADD COLUMN updated_by VARCHAR DEFAULT ''",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # Column already exists — safe to ignore
```

---

## Task 5: Update service.py to populate new fields

**Files:**
- Modify: `api/docs_/service.py`

- [ ] **Step 1: Add `datetime` import at the top of `api/docs_/service.py`**

Add to the existing imports (after line 1):

```python
from datetime import datetime
```

- [ ] **Step 2: Set `created_at` in `create_doc` — add one line before `session.add(doc)`**

Find this block in `create_doc` (around line 20):
```python
doc = Document(path=path, title=title, tags=json.dumps(tags), owner=owner, body_preview=body[:500])
session.add(doc)
```

Change to:
```python
doc = Document(path=path, title=title, tags=json.dumps(tags), owner=owner, body_preview=body[:500])
doc.created_at = datetime.utcnow()
session.add(doc)
```

- [ ] **Step 3: Set `updated_by` in `update_doc` — add one line before `await session.commit()`**

Find this block near the end of `update_doc` (around line 81):
```python
    await session.commit()
    return doc
```

Change to:
```python
    doc.updated_by = saved_by
    await session.commit()
    return doc
```

Note: this assignment is outside the `for key, value in updates.items()` loop — `updated_by` is never user-settable.

---

## Task 6: Extend GET /docs/{path} response

**Files:**
- Modify: `api/docs_/router.py`

- [ ] **Step 1: Extend the return dict in the `read` endpoint**

Find the return statement in the `read` function (lines 61–62):

```python
    return {"id": doc.id, "title": doc.title, "path": doc.path, "body": body,
            "tags": doc.tags, "owner": doc.owner, "status": doc.status}
```

Replace with:

```python
    return {
        "id": doc.id, "title": doc.title, "path": doc.path, "body": body,
        "tags": doc.tags, "owner": doc.owner, "status": doc.status,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "created_by": doc.owner or None,
        "updated_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
        "updated_by": doc.updated_by or None,
    }
```

---

## Task 7: Build API and verify backend tests pass

- [ ] **Step 1: Rebuild and restart the API**

```bash
make build-api
docker compose -f docker-compose.test.yml --env-file .env.test up -d api
```

- [ ] **Step 2: Wait for API to be ready, then run all tests**

```bash
make logs-api
# Wait until you see "Application startup complete"
make pytest
```

Expected: All 7 tests pass (5 existing + 2 new). Look for:
```
PASSED tests/test_docs.py::test_doc_get_includes_metadata
PASSED tests/test_docs.py::test_doc_update_sets_updated_by
```

- [ ] **Step 3: Commit backend changes**

```bash
git add api/db/models.py api/db/database.py api/docs_/service.py api/docs_/router.py api/tests/test_docs.py
git commit -m "feat: add created_at and updated_by metadata to documents"
```

---

## Task 8: Create vault user guide documents

**Files:**
- Create: `vault-test/docs/user-guide.md`
- Create: `vault/docs/user-guide.md`

- [ ] **Step 1: Create `vault-test/docs/user-guide.md`**

```bash
mkdir -p vault-test/docs
```

Write the file at `vault-test/docs/user-guide.md` with the content below. This exact content goes in both the test and prod vault files.

```markdown
---
title: User Guide
tags: ["docs", "help"]
owner: admin
status: current
---

# Knowledge Base — User Guide

A self-hosted knowledge management system with AI-powered search, ingestion, review, and version history. Documents are stored as Markdown files on disk, organized in folders, and indexed in a local database.

## Storing and Organizing Documents

Documents live in named folders (e.g. `personal/`, `team/processes/`). Use the sidebar on the home page to browse folders and click any document to open it. To create a new document, click **+ Ingest** in the top bar and choose either AI Ingestion or the Manual tab. Documents are written in Markdown and edited with a built-in editor.

## AI Ingestion

Paste any text — notes, meeting summaries, reference material — into the AI Ingestion tab. The AI will determine an appropriate title, folder, and whether to create a new document or update an existing one. If the AI is offline (shown by the status dot in the top bar), use the Manual tab to create a document directly.

## Search

Type a query in the search bar on the home page and press Enter or click Search. Keyword search works on all documents. When Ollama (the local AI model) is online, semantic search is also enabled, which finds conceptually similar documents even when they don't share the exact same words.

## Version History

Every time you save an edit to a document, the previous content is automatically snapshotted. Click **History** on any document to see past versions. Click **Restore** next to any version to roll back — the current content is saved as a new version first, so nothing is permanently lost.

## Review Queue

Documents can be flagged for review in two ways: the AI marks newly ingested content as needing a human review, and the nightly scheduler flags documents whose scheduled review interval has elapsed (default: 90 days). Click **Review Queue** in the top bar to see all flagged documents. Open any item to read it, then click **Mark reviewed** to clear it from the queue.

## Comments

Each document has a comment thread at the bottom of its page. Any logged-in user can add a comment. Comments can be deleted by their author, or by editors and admins. Comments are for discussion and annotation — they are not part of the document body.

## Email Ingestion

If Mailgun is configured, you can email content directly into the knowledge base. The AI processes inbound email the same way as AI Ingestion: it classifies the content and creates or updates a document. An email whitelist in the server config controls which senders are accepted. This feature requires a publicly reachable server URL (not available on localhost without a tunnel).

## User Management (Admin)

Admins can manage users via the **Users** link in the top navigation bar. You can change a user's role (reader, editor, or admin), reset their password, or delete their account. Readers can view and comment on documents. Editors can also create, edit, and ingest documents. Admins have full access including user management and document deletion.
```

- [ ] **Step 2: Copy to the prod vault**

```bash
mkdir -p vault/docs
cp vault-test/docs/user-guide.md vault/docs/user-guide.md
```

- [ ] **Step 3: Commit vault docs**

```bash
git add vault-test/docs/user-guide.md vault/docs/user-guide.md
git commit -m "docs: add user guide to vault (test and prod)"
```

---

## Task 9: Write failing E2E tests (TDD red phase)

**Files:**
- Modify: `e2e/tests/review.spec.ts`
- Modify: `e2e/tests/documents.spec.ts`
- Create: `e2e/tests/about.spec.ts`

- [ ] **Step 1: Add tooltip test to `e2e/tests/review.spec.ts`**

Add this test at the end of the `test.describe("Review Queue", ...)` block (before the closing `}`):

```ts
  test("Review Queue button has descriptive tooltip", async ({ page }) => {
    await page.goto("./");
    await page.waitForLoadState("networkidle");
    const btn = page.locator("button:has-text('Review Queue')");
    await expect(btn).toBeVisible({ timeout: 10000 });
    const title = await btn.getAttribute("title");
    expect(title).toBeTruthy();
    expect(title!.toLowerCase()).toContain("review");
  });
```

- [ ] **Step 2: Add metadata bar tests to `e2e/tests/documents.spec.ts`**

Add these two tests inside the existing `test.describe("Documents", ...)` block (before the closing `}`, after the last existing test):

```ts
  test("document metadata bar is visible on doc page", async ({ page }) => {
    await page.route("**/kms/api/docs/personal/test-meta.md", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 1, title: "Test Doc", path: "personal/test-meta.md", body: "hello",
        tags: "[]", owner: "alice@example.com", status: "current",
        created_at: "2026-02-14T10:00:00",
        created_by: "alice@example.com",
        updated_at: null,
        updated_by: null,
      }),
    }));
    await page.route("**/kms/api/comments/personal/test-meta.md", route => route.fulfill({
      status: 200, contentType: "application/json", body: "[]",
    }));
    await page.goto("./doc/personal/test-meta.md");
    await page.waitForLoadState("networkidle");
    const meta = page.locator("[data-testid='doc-metadata']");
    await expect(meta).toBeVisible({ timeout: 10000 });
    await expect(meta).toContainText("Created");
    await expect(meta).toContainText("alice@example.com");
  });

  test("metadata bar not shown when creating new doc", async ({ page }) => {
    await page.goto("./doc/new");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("[data-testid='doc-metadata']")).not.toBeVisible();
  });
```

- [ ] **Step 3: Create `e2e/tests/about.spec.ts`**

```ts
import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("About popup", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page);
  });

  test("About popup shows feature list", async ({ page }) => {
    await page.click("text=About");
    await expect(page.locator("[data-testid='about-feature-list']")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("[data-testid='about-feature-list']")).toContainText("AI-powered ingestion");
    await expect(page.locator("[data-testid='about-feature-list']")).toContainText("Review queue");
  });

  test("About popup Full details link navigates to user guide", async ({ page }) => {
    await page.route("**/kms/api/docs/docs/user-guide.md", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 99, title: "User Guide", path: "docs/user-guide.md", body: "# User Guide\n...",
        tags: "[]", owner: "admin", status: "current",
        created_at: null, created_by: null, updated_at: null, updated_by: null,
      }),
    }));
    await page.route("**/kms/api/comments/docs/user-guide.md", route => route.fulfill({
      status: 200, contentType: "application/json", body: "[]",
    }));
    await page.click("text=About");
    await page.click("text=Full details →");
    await expect(page).toHaveURL(/docs\/user-guide\.md/, { timeout: 10000 });
  });

  test("About popup closes on backdrop click", async ({ page }) => {
    await page.click("text=About");
    await expect(page.locator("h2:has-text('Knowledge Base')")).toBeVisible({ timeout: 10000 });
    await page.mouse.click(10, 10);
    await expect(page.locator("h2:has-text('Knowledge Base')")).not.toBeVisible({ timeout: 5000 });
  });
});
```

- [ ] **Step 4: Run E2E — expect the new tests to FAIL**

```bash
make e2e
```

Expected: The 6 new tests fail (tooltip missing, metadata bar missing, About has no feature list, etc.). Existing tests should still pass.

---

## Task 10: Update DocPage.tsx — metadata bar

**Files:**
- Modify: `ui/src/pages/DocPage.tsx`

- [ ] **Step 1: Extend the `Doc` interface (line 7)**

Replace:
```ts
interface Doc { title: string; body: string; path: string; }
```

With:
```ts
interface Doc {
  title: string;
  body: string;
  path: string;
  created_at?: string;
  created_by?: string;
  updated_at?: string;
  updated_by?: string;
}
```

- [ ] **Step 2: Add the metadata bar to the view-mode branch**

The view-mode branch starts around line 311 with:
```tsx
      ) : (
        <>
          <DocViewer title={doc.title} body={doc.body} />
```

Add the metadata bar between `<>` and `<DocViewer ...>`:

```tsx
      ) : (
        <>
          {!isNew && (
            <div
              data-testid="doc-metadata"
              style={{ fontSize: 12, color: "#888", marginBottom: 12 }}
            >
              Created {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : "—"} by {doc.created_by || "—"}
              {doc.updated_by && (
                <>
                  {" · "}Last updated {doc.updated_at ? new Date(doc.updated_at).toLocaleDateString() : "—"} by {doc.updated_by}
                </>
              )}
            </div>
          )}
          <DocViewer title={doc.title} body={doc.body} />
```

---

## Task 11: Update Home.tsx — tooltip and About modal

**Files:**
- Modify: `ui/src/pages/Home.tsx`

- [ ] **Step 1: Add `title` attribute to the Review Queue button**

Find the Review Queue button (around line 90):
```tsx
          <button onClick={() => navigate("/review")}>Review Queue</button>
```

Replace with:
```tsx
          <button
            title="Shows documents flagged for review — either AI-ingested content that needs a human check, or documents overdue for their scheduled review interval. Click to view the queue and mark items as reviewed."
            onClick={() => navigate("/review")}
          >
            Review Queue
          </button>
```

- [ ] **Step 2: Expand the About modal with feature list and Full details link**

Find the closing `</ul>` of the Tech Stack list inside the About modal (around line 209), which looks like:
```tsx
              </ul>
            </div>
          </div>
        </div>
      )}
```

After the `</div>` that closes the tech stack section, and before the two closing `</div>` tags that close the modal content box, insert:

```tsx
            <div style={{ marginTop: 16 }}>
              <strong>What this app does</strong>
              <ul
                data-testid="about-feature-list"
                style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13 }}
              >
                <li>Store and organize markdown documents in folders</li>
                <li>AI-powered ingestion: paste content, AI classifies and files it automatically</li>
                <li>Full-text and semantic search across all documents</li>
                <li>Version history with the ability to restore any prior version</li>
                <li>Review queue for stale or AI-created content that needs a human check</li>
                <li>Comments on documents</li>
                <li>Email ingestion via Mailgun webhook</li>
                <li>Admin user management (roles: reader, editor, admin)</li>
              </ul>
            </div>
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setShowAbout(false);
                  navigate("/doc/docs/user-guide.md");
                }}
              >
                Full details →
              </a>
            </div>
```

The modal content div should end with these two new divs, then its two closing tags. The final structure of the modal inner div should be:

```tsx
          <div onClick={e => e.stopPropagation()} style={{...}}>
            <button onClick={() => setShowAbout(false)} ...>✕</button>
            <h2 ...>Knowledge Base</h2>
            <p ...><strong>Version:</strong> 0.0.1</p>
            <p ...><strong>GitHub:</strong> ...</p>
            <div style={{ marginTop: 12 }}>
              <strong>Tech Stack</strong>
              <ul ...>...</ul>
            </div>
            <div style={{ marginTop: 16 }}>
              <strong>What this app does</strong>
              <ul data-testid="about-feature-list" ...>...</ul>
            </div>
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <a href="#" onClick={...}>Full details →</a>
            </div>
          </div>
```

---

## Task 12: Build UI and verify all tests pass

- [ ] **Step 1: Build and restart the UI**

```bash
make build-ui
docker compose -f docker-compose.test.yml --env-file .env.test up -d ui
```

- [ ] **Step 2: Run all E2E tests**

```bash
make e2e
```

Expected: All tests pass including all 6 new ones. If any test fails:
- Tooltip test fails → check `title` attribute is on the correct button in Home.tsx
- Metadata bar tests fail → check `data-testid="doc-metadata"` is present; check the `!isNew` condition
- About feature list test fails → check `data-testid="about-feature-list"` is on the `<ul>`
- Full details link test fails → check `navigate("/doc/docs/user-guide.md")` is called, and comments route mock covers `/kms/api/comments/docs/user-guide.md`

- [ ] **Step 3: Run backend tests to confirm they still pass after UI rebuild**

```bash
make pytest
```

Expected: All 7 backend tests pass.

- [ ] **Step 4: Commit frontend and E2E changes**

```bash
git add ui/src/pages/DocPage.tsx ui/src/pages/Home.tsx \
        e2e/tests/review.spec.ts e2e/tests/documents.spec.ts e2e/tests/about.spec.ts
git commit -m "feat: add doc metadata bar, review queue tooltip, and expanded About modal"
```

---

## Task 13: Push branch and open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feature/doc-metadata-tooltip-about
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "feat: doc metadata, review queue tooltip, and About help section" \
  --body "$(cat <<'EOF'
## Summary

- Every document now shows Created On/By and Last Updated On/By below the title
- Review Queue button has a hover tooltip explaining what it does and when items appear
- About popup expanded with an 8-item feature list and a "Full details →" link to an in-vault user guide

## Test plan

- [ ] `make pytest` — 7 backend tests pass (2 new: metadata fields on GET, updated_by set on PUT)
- [ ] `make e2e` — all E2E tests pass (6 new: tooltip, metadata bar x2, About popup x3)
- [ ] Manual: open a document and verify Created/Last updated line appears below title
- [ ] Manual: hover Review Queue button and verify tooltip text appears
- [ ] Manual: click About, scroll to feature list, click "Full details →", verify user guide loads

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## File Change Summary

| File | What changes |
|---|---|
| `api/db/models.py` | `created_at` (DateTime) and `updated_by` (String) columns added to `Document` |
| `api/db/database.py` | Two `ALTER TABLE` statements added in `create_db()` after `create_all` |
| `api/docs_/service.py` | `create_doc` sets `doc.created_at`; `update_doc` sets `doc.updated_by` |
| `api/docs_/router.py` | `GET /docs/{path}` return dict extended with 4 metadata fields |
| `api/tests/test_docs.py` | Two new tests: metadata on GET, updated_by on PUT |
| `ui/src/pages/DocPage.tsx` | `Doc` interface extended; metadata bar added in view mode |
| `ui/src/pages/Home.tsx` | `title` on Review Queue button; About modal gets feature list + Full details link |
| `e2e/tests/review.spec.ts` | 1 new test: tooltip presence |
| `e2e/tests/documents.spec.ts` | 2 new tests: metadata bar visible/absent |
| `e2e/tests/about.spec.ts` | New file: 3 tests (feature list, Full details nav, backdrop close) |
| `vault-test/docs/user-guide.md` | New: ~500-word user guide with YAML frontmatter |
| `vault/docs/user-guide.md` | New: same content for prod vault |
