# Design: Ingest Label Rename + About Popup

**Date:** 2026-03-09
**Status:** Approved

---

## Overview

Two small UI improvements to the Knowledge Base frontend:

1. Rename "New Document" labels to "Ingest New Information" / "+ Ingest" to accurately reflect that the create flow can update existing documents via AI ingestion.
2. Add an About link at the bottom of the Home page sidebar that opens a modal with version, GitHub repo, and tech stack info.

---

## Feature 1 — Rename "New Document" Labels

### Problem

The heading `New Document` on the create/ingest page is misleading. The AI Ingestion tab can match and update an *existing* document rather than always creating a new one. The label implies guaranteed creation.

### Changes

| File | Location | Before | After |
|------|----------|--------|-------|
| `ui/src/pages/DocPage.tsx` | Line 197 | `<h2 style={{ marginTop: 0 }}>New Document</h2>` | `<h2 style={{ marginTop: 0 }}>Ingest New Information</h2>` |
| `ui/src/pages/Home.tsx` | Line 88 | `+ New Doc` | `+ Ingest` |

No logic changes — label-only updates.

### E2E Test Updates Required

Renaming the button breaks 17 Playwright selectors across 7 test files that use `text=+ New Doc`. All must be updated to `text=+ Ingest`:

| File | Occurrences |
|------|-------------|
| `e2e/tests/document-lifecycle.spec.ts` | 8 |
| `e2e/tests/ingestion.spec.ts` | 2 |
| `e2e/tests/documents.spec.ts` | 2 |
| `e2e/tests/ingestion-real.spec.ts` | 1 |
| `e2e/tests/auth.spec.ts` | 1 |
| `e2e/tests/smoke.spec.ts` | 2 |
| `e2e/tests/review.spec.ts` | 1 |

---

## Feature 2 — About Popup in Home Sidebar

### Placement

A small `About` text link inside the sidebar `<div>` in `ui/src/pages/Home.tsx`, appended after the `Object.keys(folderTree)...map(...)` block. It is not fixed/sticky — it simply sits below the last rendered folder item in normal document flow, separated by a thin top border and small top margin. For typical vault sizes this will always be visible without scrolling.

### Trigger

Clicking the link sets local state `showAbout: boolean` to `true`.

### Modal

Implemented as inline JSX within `Home.tsx` — no new file or library needed. Follows the existing inline-style pattern used throughout the app.

- **Fixed overlay** (`position: fixed, inset: 0`) with a semi-transparent backdrop (`rgba(0,0,0,0.4)`), `zIndex: 1000`
- **Centered card** (`background: white, padding: 24, borderRadius: 6, maxWidth: 400, width: 90%`)
- **Dismiss** via ✕ button in top-right corner or clicking the backdrop
- **Content:**

```
Knowledge Base

Version: 0.0.1

GitHub
https://github.com/SirClint/knowledge-base

Tech Stack
  Frontend: React 18, TypeScript, Vite, CodeMirror 6
  Backend:  FastAPI, Python, SQLite, ChromaDB, Ollama
  Infra:    Docker, Caddy, Nginx
```

### Version Source

`Version: 0.0.1` is hardcoded inline in the modal JSX. To bump in future, update the string directly in `Home.tsx`.

### State

One new state variable in `Home` component: `const [showAbout, setShowAbout] = useState(false)`.

---

## Files Changed

- `ui/src/pages/Home.tsx` — button label, About link, About modal
- `ui/src/pages/DocPage.tsx` — heading text

No backend changes. No new files.

---

## Testing

- Manual: verify "Ingest" button navigates to `/doc/new`; verify heading reads "Ingest New Information" on that page
- Manual: About link opens modal; ✕ and backdrop close it; GitHub link opens in new tab
- E2E: update all 17 `text=+ New Doc` selectors to `text=+ Ingest` across 7 test files, then run `make e2e` to confirm all pass
- Existing E2E tests for doc create flow remain valid after selector updates
- `e2e/tests/smoke.spec.ts`: rename test description string `"AI offline warning shown on new doc page when Ollama unreachable"` → `"AI offline warning shown on ingest page when Ollama unreachable"` (not a selector, but update for consistency)
