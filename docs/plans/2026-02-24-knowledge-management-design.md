# Knowledge Management System — Design Notes
**Date:** 2026-02-24
**Status:** In progress — brainstorming phase

---

## Problem Statement

Starting a new job and need a documentation system that works regardless of what tools the company provides. Past tools used: SharePoint, Microsoft Notes (OneNote), Confluence.

**Two core problems with all past tools:**
1. **Organization entropy** — hierarchical structure degrades over time, impossible to manually reorganize at scale
2. **Staleness at scale** — no mechanism to detect or flag outdated content as the knowledge base grows

**Root cause:** Hierarchical organization is fundamentally unstable. Folders and nested pages require predicting the future — you decide upfront where something belongs, and that decision ages badly.

---

## Requirements

- **Scope:** Personal use AND team use
- **Content types:** Processes/runbooks, system architecture, task/project tracking (all of the above)
- **Portability:** Must work without company-provided infrastructure (company may have nothing set up)
- **Technical level:** High — Docker, databases, web servers all fine
- **Staleness drivers:** Systems change, process drift, no feedback loop (all of the above)
- **AI features:** Open to AI-assisted auto-tagging, staleness detection, Q&A, reorganization suggestions
- **Deployment:** Local-first (laptop), but designed portably for future server deployment (on-prem or cloud)

---

## Existing Tools Evaluated

| Tool | Key idea | Self-hostable | Team-ready | AI |
|------|----------|:---:|:---:|:---:|
| **Obsidian** | Local markdown, graph/link model | Yes (files) | Clunky | Plugins |
| **Anytype** | Object-based, graph model, open-source | Yes (sync server) | Yes | In progress |
| **Outline** | Modern wiki, Docker-deployable | Yes | Yes | Limited |
| **Logseq** | Outline-based, bi-directional links | Yes (files) | Partial | Plugins |
| **Dendron** | Schema-enforced hierarchy in VS Code | Yes (files) | Partial | No |

**Gap across all existing tools:** None fully solve staleness detection at scale.

---

## Chosen Approach

### Phase 1 — Bridge solution (this week, days to set up)
**Obsidian + git repo**
- Obsidian for reading/writing markdown files
- Git repo for version history and team sharing
- Plain markdown with YAML frontmatter (see format below)
- Zero migration cost later — Phase 2 reads the same files

### Phase 2 — Option C: Custom knowledge management system
Built specifically to solve organization entropy and staleness. Reads the same markdown files as Phase 1.

---

## Core Design Decision

**Plain markdown files with YAML frontmatter in a git repo are the permanent source of truth.**

No database lock-in. Readable with any text editor. Portable forever.

### File/Folder Structure
```
your-knowledge-base/          ← git repo
├── personal/
├── team/
│   ├── processes/
│   ├── architecture/
│   └── projects/
└── .meta/                    ← generated indexes, not committed
```

### Document Frontmatter Format
```yaml
---
title: Kubernetes Deployment Process
tags: [kubernetes, deployment, infrastructure]
created: 2024-01-15
last_reviewed: 2024-01-15
review_interval: 30d
owner: you
status: current
---
```

---

## Option C — System Components (to be designed)

The following components were identified but not yet fully designed at session end:

1. **Indexer / Watcher** — background service watching for file changes, indexing into SQLite + vector store
2. **Web UI** — self-hosted, team-accessible; primary interface for all users (replaces Confluence). Features: in-browser markdown editor (create + edit), search (keyword + semantic), document view (rendered markdown), review queue dashboard, graph view. Editor: CodeMirror or Monaco. User accounts required with three roles: Reader (view/search), Editor (read + create/edit), Admin (editor + delete + manage users).
3. **AI Service** — local AI (Ollama) for staleness detection, auto-tagging, Q&A (RAG), reorganization suggestions
4. **Review Queue** — dashboard surfacing stale docs, missing metadata, broken links, AI-flagged content
5. **Ingestion Service** — email/chat listener; AI determines create vs. update, acts immediately, replies with summary ("Updated doc: X. Done.") — no confirmation required, git is the undo. Platform TBD (design platform-agnostic).
6. **Docker Compose packaging** — for local or server deployment

### Planned Tech Stack (preliminary)
- **Backend:** Python (FastAPI)
- **Storage:** Markdown files + SQLite + local vector store (ChromaDB or similar)
- **Frontend:** TBD (lean — React or HTMX)
- **AI:** Ollama (local, no cloud dependency) with optional cloud fallback
- **Packaging:** Docker Compose

---

## Where We Left Off

All 5 sections presented and approved. Implementation plan written.

**Implementation plan:** `docs/plans/2026-03-01-knowledge-management-system.md`

---

## How to Resume

Open Claude Code in `/home/clinterrific/AI` and say:

> "Resume the knowledge management system design. Notes are at `knowledge-base/docs/plans/2026-02-24-knowledge-management-design.md`"
