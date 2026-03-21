# Design Spec: Document Metadata, Review Queue Tooltip, and About Help Section

**Date:** 2026-03-09
**Status:** Approved

---

## Overview

Three related UX improvements to the Knowledge Management System:

1. **Document metadata bar** — every document displays Created On, Created By, Last Updated On, Last Updated By below the title in view mode.
2. **Review Queue button tooltip** — a hover `title` attribute explains what the queue is and when items appear there.
3. **About panel help section** — the existing About popup gains a feature list and a link to a full user guide document stored in the vault.
4. **Automated tests** — E2E and backend tests covering all three features.

---

## 1. Document Metadata Bar

### Backend — Model (`api/db/models.py`)

Add two new columns to `Document`:

| Column | Type | Behavior |
|---|---|---|
| `created_at` | `DateTime` | Set once in `create_doc` via `datetime.utcnow()`; never overwritten by `update_doc` |
| `updated_by` | `String, default=""` | Set to editor's email on every `update_doc` call via direct attribute assignment |

`indexed_at` (existing, `onupdate=func.now()`) serves as `updated_at` — it is set by SQLAlchemy on any commit that modifies the row, so it reflects the last edit time.

`owner` (existing) serves as `created_by` — no rename, no new column.

`updated_by` must **not** be added to the `DocUpdate` Pydantic model in `router.py`. It is set server-side only, never from client input, to prevent identity forgery.

### Backend — Migration (`api/db/database.py`)

The app uses `create_all` (no Alembic). New columns will not be added to an existing database automatically. Immediately after the `await conn.run_sync(Base.metadata.create_all)` call in `create_db()`, add:

```python
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

This is idempotent: SQLite raises an error if the column already exists, which we swallow.

### Backend — Service (`api/docs_/service.py`)

- `create_doc`: before `session.add(doc)`, set `doc.created_at = datetime.utcnow()`. Import `datetime` at top of file.
- `update_doc`: before `await session.commit()`, set `doc.updated_by = saved_by`.

### Backend — Router (`api/docs_/router.py`)

The `GET /docs/{path}` handler currently returns:

```python
return {"id": doc.id, "title": doc.title, "path": doc.path, "body": body,
        "tags": doc.tags, "owner": doc.owner, "status": doc.status}
```

Extend this dict literal (do not change the serialization mechanism) to:

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

Note: `created_by` is `owner` aliased at response time; the DB column is not renamed.

`api/client.ts` does **not** need changes — `getDoc` returns untyped `any`; types are handled in the component interface.

### Frontend — DocPage (`ui/src/pages/DocPage.tsx`)

**Interface extension:**

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

**Metadata bar** — rendered in view mode (not `isNew`, not `editing`), between the toolbar `<div>` and the `<DocViewer>`. Format:

```
Created [date] by [email]  ·  Last updated [date] by [email]
```

Rules:
- `data-testid="doc-metadata"` on the container div for E2E targeting
- Font size: 12px, color: `#888`, margin-bottom: 12px
- Dates formatted with `toLocaleDateString()` (date only, no time)
- If `created_at` is null/absent, show `—` for date; if `created_by` is null/absent, show `—` for name
- If `updated_by` is null or empty string, suppress the "Last updated" segment entirely — do not show "Last updated [date] by —", as this would display the creation time as a misleading update timestamp

**Example output when doc has been edited:**
```
Created 2/14/2026 by alice@example.com  ·  Last updated 3/9/2026 by bob@example.com
```

**Example output when doc has never been edited (updated_by is null):**
```
Created 2/14/2026 by alice@example.com
```

---

## 2. Review Queue Button Tooltip

In `ui/src/pages/Home.tsx`, the `Review Queue` button (line 90) gains a `title` attribute:

```tsx
<button
  title="Shows documents flagged for review — either AI-ingested content that needs a human check, or documents overdue for their scheduled review interval. Click to view the queue and mark items as reviewed."
  onClick={() => navigate("/review")}
>
  Review Queue
</button>
```

No other changes. The tooltip renders via the browser's native `title` attribute on hover.

---

## 3. About Panel Help Section

In `ui/src/pages/Home.tsx`, expand the About modal (currently lines 179–213). The existing Version, GitHub, and Tech Stack sections are preserved. After the tech stack list, add:

### What this app does

A new section with heading and bulleted list. Wrap the `<ul>` in `data-testid="about-feature-list"`:

```tsx
<div style={{ marginTop: 16 }}>
  <strong>What this app does</strong>
  <ul data-testid="about-feature-list" style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13 }}>
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
```

### Full details link

Below the feature list, add:

```tsx
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

Call order: `setShowAbout(false)` first, then `navigate(...)`, to avoid rendering the modal during the route transition. Use React Router's `navigate` (already imported via `useNavigate`).

### Vault user guide document

Create `vault-test/docs/user-guide.md` (and `vault/docs/user-guide.md` for prod). The document must include YAML frontmatter and the following sections:

```markdown
---
title: User Guide
tags: ["docs", "help"]
owner: admin
status: current
---

# Knowledge Base — User Guide

A self-hosted knowledge management system with AI-powered search, ingestion, review, and version history.

## Storing and Organizing Documents
...folder structure, creating docs, editing...

## AI Ingestion
...paste content, AI classifies, manual fallback...

## Search
...keyword search, semantic search when AI online...

## Version History
...auto-snapshot on save, restore prior versions...

## Review Queue
...scheduled review intervals, AI-flagged docs, marking reviewed...

## Comments
...adding, deleting (own or admin), per-document thread...

## Email Ingestion
...Mailgun webhook, whitelist, how AI processes inbound email...

## User Management (Admin)
...roles (reader/editor/admin), reset password, delete user...
```

Each section should contain 2–4 sentences of prose explanation. Total length: approximately 400–600 words.

---

## 4. Automated Tests

### Backend pytest (`api/tests/test_docs.py`)

Two new test functions. Use unique paths to avoid unique constraint collisions with other tests (follow existing pattern of `f"personal/test-meta-{uuid4()}.md"` or similar).

**`test_doc_get_includes_metadata`:**
1. POST to `/docs` (editor credentials), path = `personal/meta-create-test.md`
2. GET `/docs/personal/meta-create-test.md`
3. Assert response contains `created_at` (non-null string), `created_by` (equals creator email), `updated_at` (non-null string), `updated_by` (null or empty — not set on fresh create)

**`test_doc_update_sets_updated_by`:**
1. POST to `/docs`, path = `personal/meta-update-test.md`
2. PUT `/docs/personal/meta-update-test.md` (editor credentials, change title)
3. GET `/docs/personal/meta-update-test.md`
4. Assert `updated_by` equals editor email

Both tests should clean up the vault file after (or use the existing fixture teardown pattern in `conftest.py`).

### E2E Playwright

**`e2e/tests/review.spec.ts`** — add one test:

```ts
test("Review Queue button has descriptive tooltip", async ({ page }) => {
  await registerAndLogin(page);
  const btn = page.locator("button:has-text('Review Queue')");
  const title = await btn.getAttribute("title");
  expect(title).toBeTruthy();
  expect(title!.toLowerCase()).toContain("review");
});
```

**`e2e/tests/documents.spec.ts`** — add two tests:

```ts
test("document metadata bar is visible on doc page", async ({ page }) => {
  // Mock the doc GET to return a doc with metadata
  await page.route("**/kms/api/docs/**", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      id: 1, title: "Test Doc", path: "personal/test.md", body: "hello",
      tags: "[]", owner: "alice@example.com", status: "current",
      created_at: "2026-02-14T10:00:00",
      created_by: "alice@example.com",
      updated_at: null,
      updated_by: null,
    }),
  }));
  await page.goto("./doc/personal/test.md");
  await page.waitForLoadState("networkidle");
  const meta = page.locator("[data-testid='doc-metadata']");
  await expect(meta).toBeVisible();
  await expect(meta).toContainText("Created");
  await expect(meta).toContainText("alice@example.com");
});

test("metadata bar not shown when creating new doc", async ({ page }) => {
  await page.goto("./doc/new");
  await expect(page.locator("[data-testid='doc-metadata']")).not.toBeVisible();
});
```

**`e2e/tests/about.spec.ts`** — new file:

```ts
import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("About popup", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page);
  });

  test("About popup shows feature list", async ({ page }) => {
    await page.click("text=About");
    await expect(page.locator("[data-testid='about-feature-list']")).toBeVisible();
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
    await page.click("text=About");
    await page.click("text=Full details →");
    await expect(page).toHaveURL(/docs\/user-guide\.md/);
  });

  test("About popup closes on backdrop click", async ({ page }) => {
    await page.click("text=About");
    await expect(page.locator("h2:has-text('Knowledge Base')")).toBeVisible();
    await page.mouse.click(10, 10);
    await expect(page.locator("h2:has-text('Knowledge Base')")).not.toBeVisible();
  });
});
```

---

## File Change Summary

| File | Change |
|---|---|
| `api/db/models.py` | Add `created_at` (DateTime) and `updated_by` (String) columns to `Document` |
| `api/db/database.py` | Add ALTER TABLE migration in `create_db()` after `create_all` |
| `api/docs_/service.py` | Set `created_at` on create; set `updated_by` on update |
| `api/docs_/router.py` | Extend GET dict literal with 4 new fields; confirm `updated_by` not in `DocUpdate` |
| `api/tests/test_docs.py` | Two new backend tests with unique paths |
| `ui/src/pages/DocPage.tsx` | Extend Doc interface; add metadata bar in view mode |
| `ui/src/pages/Home.tsx` | Add tooltip to Review Queue button; expand About modal with feature list + Full details link |
| `e2e/tests/review.spec.ts` | One new tooltip test |
| `e2e/tests/documents.spec.ts` | Two new metadata bar tests |
| `e2e/tests/about.spec.ts` | New file with three About popup tests |
| `vault-test/docs/user-guide.md` | New vault document (~400–600 words) |
| `vault/docs/user-guide.md` | New vault document (same content, for prod vault) |

`api/client.ts` — no changes needed (returns untyped `any`).
