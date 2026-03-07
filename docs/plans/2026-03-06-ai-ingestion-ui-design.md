# AI-Powered Document Ingestion UI Design

**Date:** 2026-03-06

## Goal

Replace the manual "New Doc" form (title + category dropdown + editor) with an AI-powered textarea where users paste raw notes or content. The AI determines whether to create a new document or update an existing one, selects the appropriate folder in the knowledge base hierarchy, and flags uncertain placements for human review.

## Architecture

Builds on the existing `ingestion/` backend module and `classify_ingestion_intent()` Ollama call. No new API routes needed. The existing `status = "needs_review"` column on `Document` is reused for AI-flagged docs.

## Backend Changes

### `api/ai/service.py`
- Enhance `classify_ingestion_intent()` system prompt to include available folder categories (`personal`, `team/processes`, `team/architecture`, `team/projects`) so Ollama picks the correct folder rather than always defaulting.
- Add `needs_review: bool` to the returned JSON (true when Ollama is uncertain about placement or action).

### `api/ingestion/service.py`
- After creating or updating the doc, if `needs_review=true`, set `doc.status = "needs_review"` on the DB record.
- Include `needs_review` in the `ingest_message` return dict.

### `api/scheduler/jobs.py`
- Update `get_overdue_docs` to also return docs with `status="needs_review"`.
- Add a `reason` field to results: `"AI-created, needs review"` vs `"Overdue for review"`.

### `api/review/router.py`
- Pass `reason` through in the queue response.

## Frontend Changes

### `ui/src/pages/DocPage.tsx`
- For `path === "new"`: replace title/category/editor form with a single large `<textarea>` and a "Process with AI" button.
- Show a processing/loading state while awaiting the Ollama response.
- On success, navigate to `/doc/{returned_path}`.

### `ui/src/api/client.ts`
- Add `ingest(message: string)` method: `POST /ingest` with `{ message }`.

### `ui/src/components/ReviewQueue.tsx` (or ReviewPage)
- Surface the `reason` field so AI-flagged docs show "AI-created, needs review" rather than a blank last-reviewed date.
- Clicking the doc title navigates to the doc for editing (existing flow, no new edit UI needed).

## Data Flow

1. User opens "New Doc" → sees large textarea
2. User pastes notes or content → clicks "Process with AI"
3. Frontend POSTs `{ message }` to `POST /ingest`
4. Backend: fetches all existing paths → calls Ollama → gets action/path/title/body/needs_review
5. Backend: creates or updates the doc; sets `status="needs_review"` if flagged
6. Backend returns `{ action, path, needs_review }`
7. Frontend navigates to `/doc/{path}`
8. If `needs_review=true`, doc also appears in Review Queue with reason label

## Non-Goals

- No preview/confirmation step before saving
- No manual fallback form
- No confidence score display in the UI
- No new edit UI in the review queue (existing doc edit flow covers this)
