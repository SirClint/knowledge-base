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
