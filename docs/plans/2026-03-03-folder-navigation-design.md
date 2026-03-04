# Folder Navigation Sidebar Design

**Date:** 2026-03-03
**Feature:** Folder structure sidebar on the search/home page

## Overview

Add a left sidebar to the Home page that displays the vault folder tree. Clicking a folder replaces search results with all documents in that folder.

## API

Add `GET /docs` endpoint to `api/docs_/router.py`.

- Returns all indexed documents: `[{"id": int, "path": str, "title": str}, ...]`
- Requires authentication (same as other doc endpoints)
- No query parameters needed

## UI Layout

Two-column layout on the Home page:

```
┌─────────────────────────────────────────────────────┐
│  Knowledge Base          [+ New Doc] [Review] [Logout]│
├──────────────┬──────────────────────────────────────┤
│ FOLDERS      │  [Search bar                        ] │
│              │                                      │
│ ▶ personal   │  • Doc title          personal/...   │
│ ▼ team       │  • Doc title          team/...       │
│   processes  │  • Doc title          team/...       │
│   architecture│                                     │
│   projects   │                                      │
└──────────────┴──────────────────────────────────────┘
```

- Left sidebar (~220px fixed width)
- Top-level folders are collapsible (toggle to show/hide subfolders)
- Clicking any folder (top-level or nested) loads its docs into the right panel
- Active folder is visually highlighted
- Clicking a folder clears the search input
- Typing a search clears the active folder selection

## Data Flow

1. **Page load** → `GET /docs` → store all docs in state → derive folder tree from paths
2. **Folder click** → filter `allDocs` where `path.startsWith(folder + "/")` → set as results, clear search query
3. **Search submit** → call existing `GET /search?q=...&mode=keyword` → set as results, clear active folder
4. Both result sets render using the same result list

Folder clicks are instant (in-memory filter, no API call). Search behavior is unchanged.

## Files to Change

- `api/docs_/router.py` — add `GET /docs` list endpoint
- `ui/src/api/client.ts` — add `listDocs()` method
- `ui/src/pages/Home.tsx` — two-column layout, sidebar, folder tree logic
