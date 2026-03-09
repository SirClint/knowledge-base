# Version History, Comments, and Email Ingestion — Design

**Date:** 2026-03-08

## Overview

Three features inspired by Atlassian Confluence gap analysis:
1. **Page version history** — snapshot every save, restore any previous version
2. **Page comments** — any authenticated user can comment on a document
3. **Email ingestion** — send/forward email to a Mailgun address, AI processes it like a web ingestion

---

## 1. Page Version History

### Data Model

New SQLite table `doc_versions`:

```
id          INTEGER PRIMARY KEY
doc_path    TEXT NOT NULL           -- vault-relative path (e.g. "personal/my-doc.md")
body        TEXT NOT NULL           -- full markdown body at time of save
saved_by    TEXT NOT NULL           -- email of user who saved
saved_at    DATETIME NOT NULL       -- UTC timestamp
```

Pruning: keep last 50 versions per document. On each save, after inserting the new snapshot, delete any versions beyond 50 (oldest first).

### API

- `GET /docs/{path:path}/versions` — list versions (id, saved_by, saved_at) — no body. Any authenticated user.
- `POST /docs/{path:path}/versions/{id}/restore` — requires editor/admin. Overwrites vault file with snapshot body. Creates a new version entry recording the restore.

### Trigger

Version snapshot is created inside `docs_/service.py` `update_doc()` **before** writing the new content to the vault file. The snapshot captures what is being replaced.

### UI

- "History" button added to the doc view toolbar (editor/admin only see Restore; readers see list only)
- Clicking opens a slide-out panel listing versions: timestamp, saved by, Restore button
- Restore triggers `POST .../versions/{id}/restore`, navigates back to doc on success

---

## 2. Page Comments

### Data Model

New SQLite table `comments`:

```
id          INTEGER PRIMARY KEY
doc_path    TEXT NOT NULL           -- vault-relative path
body        TEXT NOT NULL           -- plain text, no markdown rendering
author_email TEXT NOT NULL          -- from JWT at time of posting
created_at  DATETIME NOT NULL       -- UTC timestamp
```

### API

- `GET /docs/{path:path}/comments` — list all comments for a doc, sorted oldest-first. Any authenticated user.
- `POST /docs/{path:path}/comments` — body: `{"body": "..."}`. Any authenticated user. Max 2000 chars.
- `DELETE /comments/{id}` — author of the comment OR editor/admin. Returns 204.

### UI

- Comments section rendered below the document in `DocPage.tsx` (visible in view mode, not edit mode)
- Flat list: author email, timestamp, body, delete button (shown only to author or editor/admin)
- Textarea + "Add Comment" button at the bottom of the list
- No threading, no markdown, no reactions

---

## 3. Email Ingestion via Mailgun

### Infrastructure (one-time manual setup)

1. Create Mailgun account, add domain, configure inbound routing rule:
   - Match: all incoming to `kms@mg.<yourdomain>`
   - Action: `POST https://<your-host>/kms/api/ingest/email`
2. Add to `.env` and `.env.example`:
   ```
   MAILGUN_WEBHOOK_SIGNING_KEY=<from Mailgun dashboard>
   INGEST_EMAIL_WHITELIST=you@example.com,colleague@example.com
   ```

### API

New endpoint: `POST /ingest/email` (no auth — public, secured by Mailgun signature + whitelist)

**Request:** Mailgun webhook POST (form-encoded), key fields:
- `sender` — from address
- `subject` — email subject line
- `body-plain` — plain text body

**Processing:**
1. Verify Mailgun webhook signature using `MAILGUN_WEBHOOK_SIGNING_KEY` (HMAC-SHA256). Return 403 if invalid.
2. Check `sender` against `INGEST_EMAIL_WHITELIST`. Return 403 if not on list.
3. Combine subject + body: `f"{subject}\n\n{body_plain}"` — passed to existing `ingest_message()` service as-is.
4. Returns 200 `{"status": "queued"}` (Mailgun expects 200 or it retries).

**Config additions to `config.py`:**
```python
mailgun_webhook_signing_key: str = ""
ingest_email_whitelist: str = ""   # comma-separated emails
```

### Flow

```
Email → Mailgun → POST /ingest/email → signature check → whitelist check
→ classify_ingestion_intent() → create/update vault doc → review queue (if needed)
```

No UI changes. Ingested emails appear in the review queue exactly like web ingestions.

---

## Implementation Order

1. DB migrations — add `doc_versions` and `comments` tables
2. Version history API + tests
3. Version history UI
4. Comments API + tests
5. Comments UI
6. Email ingestion config + Mailgun signature verification
7. Email ingestion endpoint + tests
8. E2E tests for version history and comments
