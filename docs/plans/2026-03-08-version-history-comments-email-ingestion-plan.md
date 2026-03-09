# Version History, Comments, and Email Ingestion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add document version history (snapshot on save + restore), page-level comments, and email ingestion via Mailgun webhook.

**Architecture:** Two new SQLite tables (`doc_versions`, `comments`) added to the existing models; two new API routers (`/versions`, `/comments`) avoid routing conflicts with the existing `{path:path}` wildcard; `update_doc()` in `docs_/service.py` gains a `saved_by` parameter to snapshot before each save; email ingestion adds `POST /ingest/email` that verifies Mailgun HMAC signature, checks a sender whitelist, then calls the existing `ingest_message()` pipeline.

**Tech Stack:** FastAPI, SQLAlchemy (async), SQLite, React (TypeScript), Playwright E2E, pytest (asyncio), Python `hmac`/`hashlib` (stdlib — no new packages)

---

## Task 1: DB Models for doc_versions and comments

**Files:**
- Modify: `api/db/models.py`

**Step 1: Add both models**

Add to `api/db/models.py` after the `Document` class:

```python
class DocVersion(Base):
    __tablename__ = "doc_versions"

    id = Column(Integer, primary_key=True)
    doc_path = Column(String, nullable=False, index=True)
    body = Column(String, nullable=False)
    saved_by = Column(String, nullable=False, default="")
    saved_at = Column(DateTime, server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    doc_path = Column(String, nullable=False, index=True)
    body = Column(String, nullable=False)
    author_email = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
```

**Step 2: Verify tables are created on startup**

`create_db()` in `db/database.py` calls `Base.metadata.create_all` — because `DocVersion` and `Comment` extend `Base`, they will be created automatically. No migration needed.

**Step 3: Rebuild and verify**

```bash
docker compose build api && docker compose up -d api
docker compose exec api python3 -c "
from db.models import DocVersion, Comment
print('DocVersion table:', DocVersion.__tablename__)
print('Comment table:', Comment.__tablename__)
"
```
Expected: prints both table names without error.

**Step 4: Commit**

```bash
git add api/db/models.py
git commit -m "feat: add doc_versions and comments DB models"
```

---

## Task 2: Version History API

**Files:**
- Modify: `api/docs_/service.py`
- Create: `api/versions/__init__.py`
- Create: `api/versions/router.py`
- Modify: `api/main.py`
- Create: `api/tests/test_versions.py`

**Step 1: Write failing tests**

Create `api/tests/test_versions.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/register", json={"email": "ed@test.com", "password": "pass", "role": "editor"})
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "pass"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_save_creates_version(editor_client):
    # Create a doc
    await editor_client.post("/docs", json={
        "title": "My Doc", "path": "personal/ver-test.md",
        "body": "original body", "tags": [],
    })
    # Update it — should snapshot the original body
    await editor_client.put("/docs/personal/ver-test.md", json={"body": "updated body"})
    # List versions
    r = await editor_client.get("/versions/personal/ver-test.md")
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 1
    assert versions[0]["saved_by"] == "ed@test.com"


async def test_restore_version(editor_client):
    await editor_client.post("/docs", json={
        "title": "Restore Doc", "path": "personal/restore-test.md",
        "body": "v1 body", "tags": [],
    })
    await editor_client.put("/docs/personal/restore-test.md", json={"body": "v2 body"})
    versions = (await editor_client.get("/versions/personal/restore-test.md")).json()
    version_id = versions[0]["id"]

    # Restore to v1
    r = await editor_client.post(f"/versions/personal/restore-test.md/restore/{version_id}")
    assert r.status_code == 200

    # Verify doc body is back to v1
    doc = (await editor_client.get("/docs/personal/restore-test.md")).json()
    assert doc["body"] == "v1 body"


async def test_list_versions_reader_can_view(editor_client):
    await editor_client.post("/docs", json={
        "title": "Reader Doc", "path": "personal/reader-ver.md",
        "body": "body", "tags": [],
    })
    await editor_client.put("/docs/personal/reader-ver.md", json={"body": "updated"})

    # Re-login as reader
    await editor_client.post("/auth/register", json={"email": "r@test.com", "password": "pass", "role": "reader"})
    r = await editor_client.post("/auth/jwt/login", data={"username": "r@test.com", "password": "pass"})
    reader_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as rc:
        rc.headers.update(reader_headers)
        r = await rc.get("/versions/personal/reader-ver.md")
        assert r.status_code == 200


async def test_pruning_keeps_50_versions(editor_client):
    await editor_client.post("/docs", json={
        "title": "Prune Doc", "path": "personal/prune-test.md",
        "body": "v0", "tags": [],
    })
    # Create 55 versions
    for i in range(1, 56):
        await editor_client.put("/docs/personal/prune-test.md", json={"body": f"v{i}"})
    versions = (await editor_client.get("/versions/personal/prune-test.md")).json()
    assert len(versions) == 50
```

**Step 2: Run to verify they fail**

```bash
docker compose exec api pytest tests/test_versions.py -v
```
Expected: FAIL — `GET /versions/...` returns 404

**Step 3: Update `update_doc` in `docs_/service.py` to snapshot before saving**

Replace the entire `update_doc` function:

```python
async def update_doc(path: str, updates: dict, session: AsyncSession, saved_by: str = "") -> Document | None:
    doc = await get_doc(path, session)
    if not doc:
        return None

    # Snapshot current body before overwriting
    full_path = Path(settings.vault_path) / path
    if full_path.exists() and ("body" in updates or "title" in updates):
        from db.models import DocVersion
        from sqlalchemy import select, func, delete

        post = frontmatter.load(str(full_path))
        current_body = post.content

        snapshot = DocVersion(doc_path=path, body=current_body, saved_by=saved_by)
        session.add(snapshot)
        await session.flush()

        # Prune: keep only the 50 most recent versions
        subq = (
            select(DocVersion.id)
            .where(DocVersion.doc_path == path)
            .order_by(DocVersion.saved_at.desc())
            .limit(50)
        ).subquery()
        await session.execute(
            delete(DocVersion).where(
                DocVersion.doc_path == path,
                DocVersion.id.not_in(select(subq.c.id))
            )
        )

    # Apply updates
    for key, value in updates.items():
        setattr(doc, key, value)
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        if "title" in updates:
            post.metadata["title"] = updates["title"]
        if "body" in updates:
            post.content = updates["body"]
        full_path.write_text(frontmatter.dumps(post))
    await session.commit()
    return doc
```

**Step 4: Update `docs_/router.py` to pass `saved_by` to `update_doc`**

In the `update` endpoint, change:
```python
doc = await update_doc(path, updates, session)
```
To:
```python
doc = await update_doc(path, updates, session, saved_by=user.email)
```

Also add `user=Depends(current_active_user)` to the `update` endpoint signature (it currently only has `require_editor` as a dependency but doesn't capture the user object):

```python
@router.put("/{path:path}", dependencies=[Depends(require_editor)])
async def update(path: str, payload: DocUpdate, session=Depends(get_session), user=Depends(current_active_user)):
    updates = payload.model_dump(exclude_none=True)
    doc = await update_doc(path, updates, session, saved_by=user.email)
    if not doc:
        raise HTTPException(404)
    return doc
```

**Step 5: Create `api/versions/__init__.py`** (empty file)

**Step 6: Create `api/versions/router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.database import get_session
from db.models import DocVersion
from auth.users import current_active_user, require_editor, User
from docs_.service import get_doc, update_doc
from pathlib import Path
from config import settings
import frontmatter

router = APIRouter(prefix="/versions", tags=["versions"])


@router.get("/{path:path}")
async def list_versions(path: str, session: AsyncSession = Depends(get_session), _=Depends(current_active_user)):
    result = await session.execute(
        select(DocVersion)
        .where(DocVersion.doc_path == path)
        .order_by(DocVersion.saved_at.desc())
    )
    versions = result.scalars().all()
    return [
        {"id": v.id, "saved_by": v.saved_by, "saved_at": str(v.saved_at)}
        for v in versions
    ]


@router.post("/{path:path}/restore/{version_id}")
async def restore_version(
    path: str,
    version_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
):
    version = await session.get(DocVersion, version_id)
    if not version or version.doc_path != path:
        raise HTTPException(status_code=404, detail="Version not found")

    doc = await get_doc(path, session)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Snapshot current state before restoring (so restore is itself reversible)
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        current_snapshot = DocVersion(doc_path=path, body=post.content, saved_by=user.email)
        session.add(current_snapshot)

    # Write the restored body
    await update_doc(path, {"body": version.body}, session, saved_by=user.email)
    return {"restored": True, "path": path}
```

**Step 7: Register the versions router in `main.py`**

Add after the admin router block:

```python
# ── Versions routes ───────────────────────────────────────────────────────────
from versions.router import router as versions_router

app.include_router(versions_router)
```

**Step 8: Rebuild and run tests**

```bash
docker compose build api && docker compose up -d api
docker compose exec api pytest tests/test_versions.py -v
```
Expected: all 4 tests PASS

**Step 9: Run full suite**

```bash
docker compose exec api pytest -v
```
Expected: 38 existing + 4 new = 42 passed

**Step 10: Commit**

```bash
git add api/db/models.py api/docs_/service.py api/docs_/router.py api/versions/__init__.py api/versions/router.py api/tests/test_versions.py api/main.py
git commit -m "feat: document version history — snapshot on save, list, restore"
```

---

## Task 3: Version History UI

**Files:**
- Modify: `ui/src/pages/DocPage.tsx`
- Modify: `ui/src/api/client.ts`

**Step 1: Add version API methods to `client.ts`**

Add to the `api` object:

```typescript
listVersions: (path: string) => request(`/versions/${path}`),
restoreVersion: (path: string, versionId: number) => request(`/versions/${path}/restore/${versionId}`, { method: "POST" }),
```

**Step 2: Add version history panel to `DocPage.tsx`**

Read the current `DocPage.tsx` first to understand its structure. Then make these additions:

Add state variables (alongside existing ones):
```tsx
const [showHistory, setShowHistory] = useState(false);
const [versions, setVersions] = useState<{id: number; saved_by: string; saved_at: string}[]>([]);
const [loadingVersions, setLoadingVersions] = useState(false);
```

Add a `loadVersions` function:
```tsx
async function loadVersions() {
  if (!path || isNew) return;
  setLoadingVersions(true);
  try {
    const data = await api.listVersions(path);
    setVersions(data);
  } catch {
    // silently ignore — history is a non-critical feature
  } finally {
    setLoadingVersions(false);
  }
}
```

Add a `restoreVersion` function:
```tsx
async function restoreVersion(versionId: number) {
  if (!window.confirm("Restore this version? The current content will be saved as a new version first.")) return;
  try {
    await api.restoreVersion(path!, versionId);
    // Reload the doc
    const updated = await api.getDoc(path!);
    setDoc(updated);
    setShowHistory(false);
    setVersions([]);
  } catch (e: any) {
    setError(e.message ?? "Restore failed");
  }
}
```

In the toolbar buttons (the `!isNew` section at the top of the JSX), add a History button:
```tsx
{!isNew && !editing && (
  <button onClick={() => { setShowHistory(h => !h); if (!showHistory) loadVersions(); }}>
    History
  </button>
)}
```

Add the history panel just before the closing `</div>` of the main container:
```tsx
{showHistory && (
  <div style={{
    marginTop: 24, padding: 16, background: "#f8f8f8",
    borderRadius: 4, border: "1px solid #ddd"
  }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
      <strong>Version History</strong>
      <button onClick={() => setShowHistory(false)} style={{ fontSize: 11 }}>Close</button>
    </div>
    {loadingVersions && <div style={{ color: "#888", fontSize: 13 }}>Loading...</div>}
    {!loadingVersions && versions.length === 0 && (
      <div style={{ color: "#888", fontSize: 13 }}>No saved versions yet. Versions are created each time you save.</div>
    )}
    {versions.map(v => (
      <div key={v.id} style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "6px 0", borderBottom: "1px solid #eee", fontSize: 13
      }}>
        <span>
          <span style={{ color: "#555" }}>{new Date(v.saved_at).toLocaleString()}</span>
          <span style={{ color: "#888", marginLeft: 8 }}>by {v.saved_by}</span>
        </span>
        <button onClick={() => restoreVersion(v.id)} style={{ fontSize: 11 }}>Restore</button>
      </div>
    ))}
  </div>
)}
```

**Step 3: Rebuild UI and verify manually**

```bash
docker compose build ui && docker compose up -d ui
```

Navigate to any document, click "History", verify the panel opens. Save an edit, reopen History, verify a version entry appears. Click Restore, verify the doc content reverts.

**Step 4: Commit**

```bash
git add ui/src/pages/DocPage.tsx ui/src/api/client.ts
git commit -m "feat: version history UI — History panel with restore on DocPage"
```

---

## Task 4: Comments API

**Files:**
- Create: `api/comments/__init__.py`
- Create: `api/comments/router.py`
- Modify: `api/main.py`
- Create: `api/tests/test_comments.py`

**Step 1: Write failing tests**

Create `api/tests/test_comments.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/register", json={"email": "ed@test.com", "password": "pass", "role": "editor"})
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "pass"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        # Create a doc to comment on
        await c.post("/docs", json={"title": "Commented Doc", "path": "personal/commented.md", "body": "body", "tags": []})
        yield c


async def test_add_and_list_comments(editor_client):
    r = await editor_client.post("/comments/personal/commented.md", json={"body": "Great doc!"})
    assert r.status_code == 201
    r = await editor_client.get("/comments/personal/commented.md")
    assert r.status_code == 200
    comments = r.json()
    assert len(comments) == 1
    assert comments[0]["body"] == "Great doc!"
    assert comments[0]["author_email"] == "ed@test.com"


async def test_delete_own_comment(editor_client):
    r = await editor_client.post("/comments/personal/commented.md", json={"body": "to delete"})
    comment_id = r.json()["id"]
    r = await editor_client.delete(f"/comments/{comment_id}")
    assert r.status_code == 204
    comments = (await editor_client.get("/comments/personal/commented.md")).json()
    assert not any(c["id"] == comment_id for c in comments)


async def test_reader_cannot_delete_others_comment(editor_client):
    r = await editor_client.post("/comments/personal/commented.md", json={"body": "editor comment"})
    comment_id = r.json()["id"]

    # Register reader and get token
    await editor_client.post("/auth/register", json={"email": "r@test.com", "password": "pass", "role": "reader"})
    login = await editor_client.post("/auth/jwt/login", data={"username": "r@test.com", "password": "pass"})
    reader_token = login.json()["access_token"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as rc:
        rc.headers["Authorization"] = f"Bearer {reader_token}"
        r = await rc.delete(f"/comments/{comment_id}")
        assert r.status_code == 403


async def test_comment_body_max_length(editor_client):
    long_body = "x" * 2001
    r = await editor_client.post("/comments/personal/commented.md", json={"body": long_body})
    assert r.status_code == 400
```

**Step 2: Run to verify they fail**

```bash
docker compose exec api pytest tests/test_comments.py -v
```
Expected: FAIL — 404 on `/comments/*` routes

**Step 3: Create `api/comments/__init__.py`** (empty)

**Step 4: Create `api/comments/router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from db.database import get_session
from db.models import Comment
from auth.users import current_active_user, User

router = APIRouter(prefix="/comments", tags=["comments"])


class CommentCreate(BaseModel):
    body: str


@router.get("/{path:path}")
async def list_comments(path: str, session: AsyncSession = Depends(get_session), _=Depends(current_active_user)):
    result = await session.execute(
        select(Comment)
        .where(Comment.doc_path == path)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return [
        {"id": c.id, "body": c.body, "author_email": c.author_email, "created_at": str(c.created_at)}
        for c in comments
    ]


@router.post("/{path:path}", status_code=201)
async def add_comment(
    path: str,
    payload: CommentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    if len(payload.body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Comment body cannot be empty")
    if len(payload.body) > 2000:
        raise HTTPException(status_code=400, detail="Comment must be 2000 characters or fewer")
    comment = Comment(doc_path=path, body=payload.body, author_email=user.email)
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return {"id": comment.id, "body": comment.body, "author_email": comment.author_email, "created_at": str(comment.created_at)}


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    comment = await session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    # Author can delete own comment; editors and admins can delete any
    if comment.author_email != user.email and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
    await session.delete(comment)
    await session.commit()
```

**Step 5: Register comments router in `main.py`**

Add after the versions router block:

```python
# ── Comments routes ───────────────────────────────────────────────────────────
from comments.router import router as comments_router

app.include_router(comments_router)
```

**Step 6: Rebuild and run tests**

```bash
docker compose build api && docker compose up -d api
docker compose exec api pytest tests/test_comments.py -v
```
Expected: all 4 tests PASS

**Step 7: Run full suite**

```bash
docker compose exec api pytest -v
```
Expected: 42 existing + 4 new = 46 passed

**Step 8: Commit**

```bash
git add api/comments/__init__.py api/comments/router.py api/tests/test_comments.py api/main.py
git commit -m "feat: page comments API — list, add, delete with author/role guard"
```

---

## Task 5: Comments UI

**Files:**
- Modify: `ui/src/pages/DocPage.tsx`
- Modify: `ui/src/api/client.ts`

**Step 1: Add comment API methods to `client.ts`**

Add to the `api` object:

```typescript
listComments: (path: string) => request(`/comments/${path}`),
addComment: (path: string, body: string) => request(`/comments/${path}`, { method: "POST", body: JSON.stringify({ body }) }),
deleteComment: (id: number) => request(`/comments/${id}`, { method: "DELETE" }),
```

**Step 2: Add comments section to `DocPage.tsx`**

Add state variables:
```tsx
const [comments, setComments] = useState<{id: number; body: string; author_email: string; created_at: string}[]>([]);
const [newComment, setNewComment] = useState("");
const [commentError, setCommentError] = useState("");
const currentUserEmail = localStorage.getItem("role") !== null
  ? undefined  // will match by email from /users/me — use api.getMe() below
  : undefined;
```

Actually, simpler: store the current user's email in localStorage at login (it's already stored as `role`). Add `email` to localStorage in `client.ts` login function:

In `client.ts`, in the `login` function after `localStorage.setItem("role", me.role ?? "reader")` add:
```typescript
localStorage.setItem("email", me.email ?? "");
```

Then in `DocPage.tsx`:
```tsx
const currentEmail = localStorage.getItem("email") ?? "";
const currentRole = localStorage.getItem("role") ?? "reader";
```

Add `loadComments` function:
```tsx
async function loadComments() {
  if (!path || isNew) return;
  try {
    const data = await api.listComments(path);
    setComments(data);
  } catch {
    // non-critical
  }
}
```

Call `loadComments()` in the existing `useEffect` that loads the doc:
```tsx
useEffect(() => {
  if (!isNew && path) {
    api.getDoc(path).then(setDoc).catch(() => setError("Document not found"));
    loadComments();
  }
}, [path, isNew]);
```

Add `submitComment` function:
```tsx
async function submitComment() {
  if (!newComment.trim()) return;
  setCommentError("");
  try {
    await api.addComment(path!, newComment);
    setNewComment("");
    loadComments();
  } catch (e: any) {
    setCommentError(e.message ?? "Failed to add comment");
  }
}

async function removeComment(id: number) {
  try {
    await api.deleteComment(id);
    loadComments();
  } catch (e: any) {
    setCommentError(e.message ?? "Failed to delete comment");
  }
}
```

Add the comments section in the JSX — render it when `!isNew && !editing` (view mode only), after the `<DocViewer>` component and before the history panel:

```tsx
{!isNew && !editing && (
  <div style={{ marginTop: 32, borderTop: "1px solid #eee", paddingTop: 24 }}>
    <strong style={{ fontSize: 15 }}>Comments {comments.length > 0 && `(${comments.length})`}</strong>
    <div style={{ marginTop: 12 }}>
      {comments.map(c => (
        <div key={c.id} style={{
          padding: "10px 0", borderBottom: "1px solid #f0f0f0", fontSize: 14
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <span style={{ fontWeight: "bold", fontSize: 12, color: "#555" }}>{c.author_email}</span>
              <span style={{ color: "#aaa", fontSize: 11, marginLeft: 8 }}>
                {new Date(c.created_at).toLocaleString()}
              </span>
            </div>
            {(c.author_email === currentEmail || currentRole === "editor" || currentRole === "admin") && (
              <button onClick={() => removeComment(c.id)} style={{ fontSize: 11, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}>
                Delete
              </button>
            )}
          </div>
          <div style={{ marginTop: 4 }}>{c.body}</div>
        </div>
      ))}
    </div>
    <div style={{ marginTop: 16 }}>
      <textarea
        value={newComment}
        onChange={e => setNewComment(e.target.value)}
        placeholder="Add a comment..."
        style={{ display: "block", width: "100%", height: 80, padding: 8, fontSize: 13, boxSizing: "border-box", resize: "vertical" }}
      />
      {commentError && <div style={{ color: "red", fontSize: 12, marginTop: 4 }}>{commentError}</div>}
      <button
        onClick={submitComment}
        disabled={!newComment.trim()}
        style={{ marginTop: 6, fontSize: 13 }}
      >
        Add Comment
      </button>
    </div>
  </div>
)}
```

**Step 3: Rebuild and verify**

```bash
docker compose build ui && docker compose up -d ui
```

Navigate to any document in view mode. Verify:
- Comments section appears below the document
- Can add a comment, it appears in the list
- Author can delete their own comment
- Comments are plain text (no markdown rendering)

**Step 4: Commit**

```bash
git add ui/src/pages/DocPage.tsx ui/src/api/client.ts
git commit -m "feat: comments UI — add and delete comments on document view page"
```

---

## Task 6: Email Ingestion via Mailgun

**Files:**
- Modify: `api/config.py`
- Modify: `api/ingestion/router.py`
- Create: `api/tests/test_email_ingestion.py`

**Step 1: Add config settings**

In `api/config.py`, add two new fields to the `Settings` class:

```python
mailgun_webhook_signing_key: str = ""
ingest_email_whitelist: str = ""  # comma-separated emails, e.g. "you@example.com,other@example.com"
```

Add to `.env.example`:
```
MAILGUN_WEBHOOK_SIGNING_KEY=
INGEST_EMAIL_WHITELIST=
```

**Step 2: Write failing tests**

Create `api/tests/test_email_ingestion.py`:

```python
import pytest
import hmac
import hashlib
import time
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app


def make_mailgun_signature(signing_key: str, timestamp: str, token: str) -> str:
    return hmac.new(
        key=signing_key.encode(),
        msg=f"{timestamp}{token}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


@pytest.fixture
async def client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_email_ingestion_valid(client):
    signing_key = "test-signing-key"
    timestamp = str(int(time.time()))
    token = "test-token-abc123"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    mock_result = {"action": "create", "path": "personal/test.md", "needs_review": False, "message": "Created doc: Test."}

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"), \
         patch("ingestion.service.ingest_message", new=AsyncMock(return_value=mock_result)):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            "sender": "sender@example.com",
            "subject": "Meeting Notes",
            "body-plain": "These are the notes from today's meeting.",
        })
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_email_ingestion_invalid_signature(client):
    timestamp = str(int(time.time()))
    with patch("config.settings.mailgun_webhook_signing_key", "real-key"), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": "sometoken",
            "signature": "wrongsignature",
            "sender": "sender@example.com",
            "subject": "Test",
            "body-plain": "body",
        })
    assert r.status_code == 403


async def test_email_ingestion_sender_not_whitelisted(client):
    signing_key = "test-key"
    timestamp = str(int(time.time()))
    token = "tok"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "allowed@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            "sender": "notallowed@example.com",
            "subject": "Test",
            "body-plain": "body",
        })
    assert r.status_code == 403


async def test_email_ingestion_no_signing_key_configured(client):
    """When no signing key is configured, reject all requests."""
    with patch("config.settings.mailgun_webhook_signing_key", ""), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": "12345",
            "token": "tok",
            "signature": "sig",
            "sender": "sender@example.com",
            "subject": "Test",
            "body-plain": "body",
        })
    assert r.status_code == 403
```

**Step 3: Run to verify they fail**

```bash
docker compose exec api pytest tests/test_email_ingestion.py -v
```
Expected: FAIL — 404 on `/ingest/email`

**Step 4: Add the email endpoint to `api/ingestion/router.py`**

Replace the entire file:

```python
import hmac
import hashlib
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from db.database import get_session
from ingestion.service import ingest_message
from auth.users import current_active_user
from config import settings

router = APIRouter(prefix="/ingest", tags=["ingestion"])


class IngestPayload(BaseModel):
    message: str
    reply_to: str = ""


def _verify_mailgun_signature(signing_key: str, timestamp: str, token: str, signature: str) -> bool:
    """Verify Mailgun webhook HMAC-SHA256 signature."""
    if not signing_key:
        return False
    try:
        # Reject timestamps older than 15 minutes
        if abs(int(timestamp) - int(time.time())) > 900:
            return False
    except (ValueError, TypeError):
        return False
    computed = hmac.new(
        key=signing_key.encode(),
        msg=f"{timestamp}{token}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("")
async def ingest(payload: IngestPayload, session=Depends(get_session), user=Depends(current_active_user)):
    try:
        result = await ingest_message(payload.message, session)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/email")
async def ingest_email(request: Request, session=Depends(get_session)):
    form = await request.form()
    timestamp = form.get("timestamp", "")
    token = form.get("token", "")
    signature = form.get("signature", "")
    sender = form.get("sender", "")
    subject = form.get("subject", "")
    body_plain = form.get("body-plain", "")

    # Verify Mailgun signature
    if not _verify_mailgun_signature(settings.mailgun_webhook_signing_key, timestamp, token, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Check sender whitelist
    whitelist = [e.strip().lower() for e in settings.ingest_email_whitelist.split(",") if e.strip()]
    if not whitelist or sender.lower() not in whitelist:
        raise HTTPException(status_code=403, detail="Sender not authorized")

    # Combine subject + body and pass through existing AI ingestion pipeline
    message = f"{subject}\n\n{body_plain}".strip() if subject else body_plain
    try:
        await ingest_message(message, session)
    except ValueError as e:
        # Log but return 200 so Mailgun doesn't retry
        print(f"Email ingestion error: {e}")
    return {"status": "queued"}
```

**Step 5: Rebuild and run tests**

```bash
docker compose build api && docker compose up -d api
docker compose exec api pytest tests/test_email_ingestion.py -v
```
Expected: all 4 tests PASS

**Step 6: Run full suite**

```bash
docker compose exec api pytest -v
```
Expected: 46 existing + 4 new = 50 passed

**Step 7: Commit**

```bash
git add api/config.py api/ingestion/router.py api/tests/test_email_ingestion.py .env.example
git commit -m "feat: email ingestion via Mailgun webhook — signature verification and sender whitelist"
```

---

## Task 7: E2E Tests for Version History and Comments

**Files:**
- Create: `e2e/tests/version-history.spec.ts`
- Create: `e2e/tests/comments.spec.ts`

**Step 1: Create version history E2E tests**

Create `e2e/tests/version-history.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test.describe("Version History", () => {
  test("History button appears on document view", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });
    await page.goto("./doc/new");
    await page.click("text=Manual");
    await page.fill('input[placeholder="Document title"]', "History Test Doc");
    await page.locator("select").selectOption("personal");
    await page.click("text=Create Document");
    await page.waitForURL(/\/kms\/doc\//);
    await expect(page.locator("button", { hasText: "History" })).toBeVisible();
  });

  test("History panel shows versions after an edit", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    // Create a doc via API
    const token = localStorage ? localStorage.getItem("token") : null;
    const docPath = `personal/ver-e2e-${Date.now()}.md`;
    await page.request.post("http://localhost:8080/kms/api/docs", {
      data: { title: "Ver E2E Doc", path: docPath, body: "original", tags: [] },
      headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("token"))}` },
    });

    // Edit and save via UI
    await page.goto(`./doc/${docPath}`);
    await page.click("text=Edit");
    // CodeMirror editor — click and clear, then type
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("updated content");
    await page.click("text=Save");

    // Open history
    await page.click("text=History");
    await expect(page.locator("text=by")).toBeVisible({ timeout: 5000 });
  });
});
```

**Step 2: Create comments E2E tests**

Create `e2e/tests/comments.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("Comments", () => {
  test("can add and see a comment on a document", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const docPath = `personal/comment-e2e-${Date.now()}.md`;
    await page.request.post("http://localhost:8080/kms/api/docs", {
      data: { title: "Comment E2E Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("token"))}` },
    });

    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=Add a comment...")).toBeVisible();

    await page.fill('textarea[placeholder="Add a comment..."]', "This is my comment");
    await page.click("text=Add Comment");

    await expect(page.locator("text=This is my comment")).toBeVisible();
  });

  test("comment author can delete their own comment", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const docPath = `personal/del-comment-e2e-${Date.now()}.md`;
    await page.request.post("http://localhost:8080/kms/api/docs", {
      data: { title: "Del Comment Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("token"))}` },
    });

    await page.goto(`./doc/${docPath}`);
    await page.fill('textarea[placeholder="Add a comment..."]', "delete me");
    await page.click("text=Add Comment");
    await expect(page.locator("text=delete me")).toBeVisible();

    await page.click("button:has-text('Delete')");
    await expect(page.locator("text=delete me")).not.toBeVisible();
  });
});
```

**Step 3: Run new E2E tests**

```bash
cd /home/clinterrific/AI/knowledge-base/e2e && npx playwright test version-history.spec.ts comments.spec.ts
```
Expected: all tests pass (some may be flaky due to CodeMirror interaction — adjust if needed)

**Step 4: Run full E2E suite**

```bash
npx playwright test
```
Expected: all tests pass

**Step 5: Commit**

```bash
git add e2e/tests/version-history.spec.ts e2e/tests/comments.spec.ts
git commit -m "test: E2E tests for version history and comments"
```

---

## Final Verification

```bash
# Backend
docker compose exec api pytest -v
# Expected: 50 passed

# E2E
cd e2e && npx playwright test
# Expected: all pass

# Push
git push
```

---

## Mailgun Setup Instructions (Manual, One-Time)

You'll set up **two Mailgun routes** — one pointing at your test environment (port 8081) and one at prod (port 8080). Both use the same Mailgun signing key but different recipient addresses and different `.env` files.

### Step 1: Mailgun account and domain

1. Sign up at https://www.mailgun.com (free tier)
2. Add your domain (or use the Mailgun sandbox domain for initial testing)
3. Go to **Settings → API Security**, copy the **HTTP webhook signing key** — you'll use this in both environments

### Step 2: Create two inbound routes

Go to **Receiving → Routes** and create two routes:

**Test route:**
- Expression: `match_recipient("kms-test@mg.yourdomain.com")`
- Action: `forward("http://yourhost:8081/kms/api/ingest/email")`

**Prod route:**
- Expression: `match_recipient("kms@mg.yourdomain.com")`
- Action: `forward("http://yourhost:8080/kms/api/ingest/email")`

> Note: Mailgun must be able to reach your host over HTTP/HTTPS. If running locally without a public URL, use a tunnel like [ngrok](https://ngrok.com) during setup: `ngrok http 8080` gives you a public URL to use in the route.

### Step 3: Configure each environment

**Test environment (`.env.test`):**
```
MAILGUN_WEBHOOK_SIGNING_KEY=<your signing key>
INGEST_EMAIL_WHITELIST=you@youremail.com
```

**Production environment (`.env`):**
```
MAILGUN_WEBHOOK_SIGNING_KEY=<your signing key>
INGEST_EMAIL_WHITELIST=you@youremail.com
```

### Step 4: Restart the API in each environment

```bash
# Test
docker compose -f docker-compose.test.yml up -d api

# Prod
docker compose up -d api
```

### Step 5: Verify

Send a test email to `kms-test@mg.yourdomain.com` and check the review queue at http://localhost:8081/kms/review.

Once confirmed working in test, send to `kms@mg.yourdomain.com` and check http://localhost:8080/kms/review.
