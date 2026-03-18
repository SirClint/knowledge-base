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
| `ui/src/pages/DocPage.tsx` | Line 197 | `<h2>New Document</h2>` | `<h2>Ingest New Information</h2>` |
| `ui/src/pages/Home.tsx` | Line 88 | `+ New Doc` | `+ Ingest` |

No logic changes — label-only updates.

---

## Feature 2 — About Popup in Home Sidebar

### Placement

A small `About` text link at the bottom of the sidebar in `ui/src/pages/Home.tsx`, below the folder list, separated by a thin top border and small top margin.

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
- Existing E2E tests cover the create-doc flow and should not need changes (no selectors on these labels)
