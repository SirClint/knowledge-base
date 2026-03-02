# Knowledge Management System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a self-hosted, Confluence-replacement knowledge management system with AI-assisted staleness detection, in-browser editing, and team user accounts.

**Architecture:** Plain markdown files in a git repo are the permanent source of truth. A FastAPI backend indexes files into SQLite (metadata) and ChromaDB (vectors), serves a REST API, and runs background jobs for staleness detection. A React frontend provides the full editing/search/review experience via browser.

**Tech Stack:** Python 3.12, FastAPI, FastAPI-Users, SQLite, ChromaDB, Watchdog, APScheduler, GitPython, Ollama (Llama 3.2 + nomic-embed-text), React 18, CodeMirror 6, Docker Compose, Caddy

---

## Project Structure

```
knowledge-base/
├── docker-compose.yml
├── .env.example
├── caddy/
│   └── Caddyfile
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── main.py
│   ├── config.py
│   ├── db/
│   │   ├── database.py
│   │   └── models.py
│   ├── auth/
│   │   └── users.py
│   ├── docs_/              ← "docs" conflicts with Python stdlib
│   │   ├── router.py
│   │   ├── service.py
│   │   └── parser.py
│   ├── search/
│   │   └── service.py
│   ├── ai/
│   │   └── service.py
│   ├── watcher/
│   │   └── watcher.py
│   ├── scheduler/
│   │   └── jobs.py
│   ├── ingestion/
│   │   └── service.py
│   └── tests/
│       ├── conftest.py
│       ├── test_parser.py
│       ├── test_docs.py
│       ├── test_search.py
│       ├── test_auth.py
│       ├── test_ai.py
│       └── test_ingestion.py
├── ui/
│   ├── Dockerfile
│   ├── package.json
│   ├── nginx.conf
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts
│       ├── components/
│       │   ├── Editor.tsx
│       │   ├── DocViewer.tsx
│       │   ├── SearchBar.tsx
│       │   └── ReviewQueue.tsx
│       └── pages/
│           ├── Login.tsx
│           ├── Home.tsx
│           ├── DocPage.tsx
│           └── ReviewPage.tsx
└── vault/                  ← the actual markdown knowledge base
    ├── personal/
    └── team/
        ├── processes/
        ├── architecture/
        └── projects/
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `api/requirements.txt`
- Create: `api/pytest.ini`
- Create: `api/config.py`
- Create: `api/main.py`
- Create: `vault/team/processes/.gitkeep`
- Create: `vault/team/architecture/.gitkeep`
- Create: `vault/team/projects/.gitkeep`
- Create: `vault/personal/.gitkeep`

**Step 1: Create `.env.example`**

```
SECRET_KEY=changeme
VAULT_PATH=/vault
OLLAMA_URL=http://ollama:11434
DATABASE_URL=sqlite:////data/kb.db
CHROMADB_PATH=/data/chroma
```

**Step 2: Create `api/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
fastapi-users[sqlalchemy]==13.0.0
sqlalchemy==2.0.36
aiosqlite==0.20.0
chromadb==0.5.20
watchdog==4.0.2
apscheduler==3.10.4
gitpython==3.1.43
httpx==0.27.2
python-frontmatter==1.1.0
python-multipart==0.0.12
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

**Step 3: Create `api/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

**Step 4: Create `api/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    secret_key: str = "changeme"
    vault_path: str = "/vault"
    ollama_url: str = "http://ollama:11434"
    database_url: str = "sqlite+aiosqlite:////data/kb.db"
    chromadb_path: str = "/data/chroma"

    class Config:
        env_file = ".env"

settings = Settings()
```

**Step 5: Create `api/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Knowledge Base API")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 6: Create `docker-compose.yml`**

```yaml
services:
  api:
    build: ./api
    volumes:
      - ./vault:/vault
      - kb_data:/data
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - ollama
      - chromadb

  ui:
    build: ./ui
    ports:
      - "3000:80"

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"

  chromadb:
    image: chromadb/chroma:latest
    volumes:
      - kb_data:/chroma/chroma
    ports:
      - "8001:8000"

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data

volumes:
  kb_data:
  ollama_data:
  caddy_data:
```

**Step 7: Create `api/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Step 8: Create vault directory structure**

```bash
mkdir -p vault/team/processes vault/team/architecture vault/team/projects vault/personal
touch vault/team/processes/.gitkeep vault/team/architecture/.gitkeep vault/team/projects/.gitkeep vault/personal/.gitkeep
```

**Step 9: Verify the API starts**

```bash
cd api && pip install -r requirements.txt && uvicorn main:app --port 8000
```
Expected: `Application startup complete` and `GET /health` returns `{"status": "ok"}`

**Step 10: Commit**

```bash
git add docker-compose.yml .env.example api/ vault/
git commit -m "feat: project scaffold with FastAPI, Docker Compose, vault structure"
```

---

## Task 2: Markdown Parser

**Files:**
- Create: `api/docs_/parser.py`
- Create: `api/tests/conftest.py`
- Create: `api/tests/test_parser.py`

**Step 1: Write the failing tests**

```python
# api/tests/test_parser.py
import pytest
from docs_.parser import parse_doc, ParsedDoc
from pathlib import Path
import tempfile, os

SAMPLE_DOC = """\
---
title: Kubernetes Deploy
tags: [kubernetes, deployment]
created: 2024-01-15
last_reviewed: 2024-01-15
review_interval: 30d
owner: alice
status: current
---

# Kubernetes Deploy

Steps to deploy to production.
"""

def test_parse_frontmatter():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE_DOC)
        path = f.name
    try:
        doc = parse_doc(Path(path))
        assert doc.title == "Kubernetes Deploy"
        assert "kubernetes" in doc.tags
        assert doc.owner == "alice"
        assert doc.status == "current"
        assert doc.review_interval == "30d"
    finally:
        os.unlink(path)

def test_parse_body():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE_DOC)
        path = f.name
    try:
        doc = parse_doc(Path(path))
        assert "Steps to deploy" in doc.body
    finally:
        os.unlink(path)

def test_parse_missing_frontmatter():
    content = "# Just a title\n\nSome content."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        path = f.name
    try:
        doc = parse_doc(Path(path))
        assert doc.title == ""
        assert doc.tags == []
    finally:
        os.unlink(path)
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_parser.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'docs_'`

**Step 3: Implement `api/docs_/parser.py`**

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import frontmatter

@dataclass
class ParsedDoc:
    path: Path
    title: str = ""
    tags: list[str] = field(default_factory=list)
    created: Optional[str] = None
    last_reviewed: Optional[str] = None
    review_interval: str = "90d"
    owner: str = ""
    status: str = "current"
    body: str = ""

def parse_doc(path: Path) -> ParsedDoc:
    post = frontmatter.load(str(path))
    meta = post.metadata
    return ParsedDoc(
        path=path,
        title=meta.get("title", ""),
        tags=meta.get("tags", []),
        created=str(meta["created"]) if "created" in meta else None,
        last_reviewed=str(meta["last_reviewed"]) if "last_reviewed" in meta else None,
        review_interval=meta.get("review_interval", "90d"),
        owner=meta.get("owner", ""),
        status=meta.get("status", "current"),
        body=post.content,
    )
```

Also create `api/docs_/__init__.py` (empty).

**Step 4: Run tests to verify they pass**

```bash
cd api && pytest tests/test_parser.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add api/docs_/ api/tests/
git commit -m "feat: markdown parser with frontmatter extraction"
```

---

## Task 3: SQLite Database + Models

**Files:**
- Create: `api/db/database.py`
- Create: `api/db/models.py`
- Create: `api/db/__init__.py`

**Step 1: Write the failing test**

```python
# api/tests/test_db.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base, Document

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s
    await engine.dispose()

async def test_create_document(session):
    doc = Document(
        path="team/processes/deploy.md",
        title="Deploy Process",
        tags='["deployment"]',
        owner="alice",
        status="current",
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    assert doc.id is not None
    assert doc.title == "Deploy Process"
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_db.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement `api/db/models.py`**

```python
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, default="")
    tags = Column(String, default="[]")      # JSON-encoded list
    owner = Column(String, default="")
    status = Column(String, default="current")
    created = Column(String, nullable=True)
    last_reviewed = Column(String, nullable=True)
    review_interval = Column(String, default="90d")
    body_preview = Column(String, default="")  # first 500 chars for list views
    indexed_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

Create `api/db/__init__.py` (empty).

**Step 4: Implement `api/db/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.models import Base
from config import settings

engine = create_async_engine(settings.database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def create_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
```

**Step 5: Run tests to verify they pass**

```bash
cd api && pytest tests/test_db.py -v
```
Expected: PASSED

**Step 6: Commit**

```bash
git add api/db/ api/tests/test_db.py
git commit -m "feat: SQLite models and async database setup"
```

---

## Task 4: File Watcher + Indexer

**Files:**
- Create: `api/watcher/watcher.py`
- Create: `api/watcher/__init__.py`
- Create: `api/tests/test_watcher.py`

**Step 1: Write the failing test**

```python
# api/tests/test_watcher.py
import pytest
from pathlib import Path
import tempfile, os
from watcher.watcher import index_file, index_vault
from db.models import Document
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()

SAMPLE = """\
---
title: Test Doc
tags: [test]
owner: bob
status: current
---
Body content here.
"""

async def test_index_file_creates_record(session):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE)
        path = Path(f.name)
    try:
        await index_file(path, session)
        from sqlalchemy import select
        result = await session.execute(select(Document).where(Document.title == "Test Doc"))
        doc = result.scalar_one_or_none()
        assert doc is not None
        assert doc.owner == "bob"
    finally:
        os.unlink(path)

async def test_index_file_updates_existing(session):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE)
        path = Path(f.name)
    try:
        await index_file(path, session)
        updated = SAMPLE.replace("title: Test Doc", "title: Updated Doc")
        path.write_text(updated)
        await index_file(path, session)
        from sqlalchemy import select, func
        result = await session.execute(select(func.count()).select_from(Document))
        count = result.scalar()
        assert count == 1  # updated, not duplicated
    finally:
        os.unlink(path)
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_watcher.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement `api/watcher/watcher.py`**

```python
import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document
from docs_.parser import parse_doc

async def index_file(path: Path, session: AsyncSession) -> Document:
    parsed = parse_doc(path)
    result = await session.execute(
        select(Document).where(Document.path == str(path))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        doc = Document(path=str(path))
        session.add(doc)
    doc.title = parsed.title
    doc.tags = json.dumps(parsed.tags)
    doc.owner = parsed.owner
    doc.status = parsed.status
    doc.created = parsed.created
    doc.last_reviewed = parsed.last_reviewed
    doc.review_interval = parsed.review_interval
    doc.body_preview = parsed.body[:500]
    await session.commit()
    return doc

async def index_vault(vault_path: Path, session: AsyncSession):
    for md_file in vault_path.rglob("*.md"):
        await index_file(md_file, session)
```

Create `api/watcher/__init__.py` (empty).

**Step 4: Run tests to verify they pass**

```bash
cd api && pytest tests/test_watcher.py -v
```
Expected: 2 PASSED

**Step 5: Wire watcher into `main.py` startup**

```python
# api/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from db.database import create_db
from config import settings
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db()
    # Index vault on startup
    from db.database import async_session_maker
    from watcher.watcher import index_vault
    async with async_session_maker() as session:
        await index_vault(Path(settings.vault_path), session)
    yield

app = FastAPI(title="Knowledge Base API", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 6: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 7: Commit**

```bash
git add api/watcher/ api/tests/test_watcher.py api/main.py
git commit -m "feat: file watcher and vault indexer"
```

---

## Task 5: ChromaDB Vector Indexing

**Files:**
- Create: `api/search/service.py`
- Create: `api/search/__init__.py`
- Create: `api/tests/test_search.py`

**Step 1: Write the failing test**

```python
# api/tests/test_search.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from search.service import embed_doc, search_semantic

async def test_embed_doc_calls_ollama():
    with patch("search.service.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        result = await embed_doc("some text about kubernetes")
        assert isinstance(result, list)
        assert len(result) == 3

async def test_search_semantic_returns_results():
    with patch("search.service.get_chroma_collection") as mock_col:
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{"path": "team/processes/deploy.md"}, {"path": "team/architecture/infra.md"}]],
        }
        mock_col.return_value = mock_collection
        with patch("search.service.embed_doc", new=AsyncMock(return_value=[0.1, 0.2])):
            results = await search_semantic("how do I deploy?", n_results=2)
            assert len(results) == 2
            assert results[0]["path"] == "team/processes/deploy.md"
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_search.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement `api/search/service.py`**

```python
import httpx
import chromadb
from config import settings

def get_chroma_collection():
    client = chromadb.PersistentClient(path=settings.chromadb_path)
    return client.get_or_create_collection("documents")

async def embed_doc(text: str) -> list[float]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=30,
        )
        return response.json()["embedding"]

async def index_doc_vectors(doc_id: str, path: str, text: str):
    embedding = await embed_doc(text)
    collection = get_chroma_collection()
    collection.upsert(
        ids=[doc_id],
        embeddings=[embedding],
        metadatas=[{"path": path}],
    )

async def search_semantic(query: str, n_results: int = 10) -> list[dict]:
    embedding = await embed_doc(query)
    collection = get_chroma_collection()
    results = collection.query(query_embeddings=[embedding], n_results=n_results)
    return [
        {"path": meta["path"], "score": 1 - dist}
        for meta, dist in zip(results["metadatas"][0], results["distances"][0])
    ]
```

Create `api/search/__init__.py` (empty).

**Step 4: Run tests to verify they pass**

```bash
cd api && pytest tests/test_search.py -v
```
Expected: 2 PASSED

**Step 5: Update watcher to also index vectors**

In `api/watcher/watcher.py`, update `index_file` to call `index_doc_vectors` after committing:

```python
# add after await session.commit():
from search.service import index_doc_vectors
await index_doc_vectors(str(doc.id), str(path), parsed.body)
```

**Step 6: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 7: Commit**

```bash
git add api/search/ api/tests/test_search.py api/watcher/watcher.py
git commit -m "feat: ChromaDB vector indexing and semantic search"
```

---

## Task 6: User Auth

**Files:**
- Create: `api/auth/users.py`
- Create: `api/auth/__init__.py`
- Create: `api/tests/test_auth.py`

**Step 1: Write the failing test**

```python
# api/tests/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

async def test_register_and_login(client):
    # Register
    r = await client.post("/auth/register", json={
        "email": "alice@example.com",
        "password": "password123",
        "role": "editor",
    })
    assert r.status_code == 201

    # Login
    r = await client.post("/auth/jwt/login", data={
        "username": "alice@example.com",
        "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()

async def test_reader_cannot_create(client):
    await client.post("/auth/register", json={
        "email": "reader@example.com",
        "password": "password123",
        "role": "reader",
    })
    login = await client.post("/auth/jwt/login", data={
        "username": "reader@example.com",
        "password": "password123",
    })
    token = login.json()["access_token"]
    r = await client.post(
        "/docs",
        json={"title": "Test", "body": "content"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_auth.py -v
```
Expected: FAIL

**Step 3: Implement `api/auth/users.py`**

```python
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import JWTStrategy, AuthenticationBackend, BearerTransport
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import Column, String
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Base
from config import settings

class User(Base):
    __tablename__ = "users"
    # FastAPIUsers provides id, email, hashed_password, is_active, is_verified, is_superuser
    role = Column(String, default="reader")  # reader | editor | admin

# Full FastAPIUsers setup omitted for brevity — follow fastapi-users docs for SQLAlchemy async setup
# Key: add /auth/register and /auth/jwt/login routes to main.py
```

> Note: Follow the [FastAPI-Users SQLAlchemy async guide](https://fastapi-users.github.io/fastapi-users/latest/configuration/databases/sqlalchemy/) exactly. It requires a `UserDatabase` adapter, `UserManager`, and wiring into the FastAPI app lifespan.

**Step 4: Add role-based dependency to `api/auth/users.py`**

```python
from fastapi import Depends, HTTPException, status

def require_role(*roles: str):
    async def check(user=Depends(current_active_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check

require_editor = require_role("editor", "admin")
require_admin = require_role("admin")
```

**Step 5: Run tests to verify they pass**

```bash
cd api && pytest tests/test_auth.py -v
```
Expected: 2 PASSED

**Step 6: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 7: Commit**

```bash
git add api/auth/ api/tests/test_auth.py api/main.py api/db/models.py
git commit -m "feat: user auth with JWT and role-based permissions (reader/editor/admin)"
```

---

## Task 7: Documents API (CRUD)

**Files:**
- Create: `api/docs_/router.py`
- Create: `api/docs_/service.py`
- Create: `api/tests/test_docs.py`

**Step 1: Write the failing tests**

```python
# api/tests/test_docs.py
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture
async def editor_client():
    # Register editor, login, return authenticated client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/register", json={"email": "ed@test.com", "password": "pass", "role": "editor"})
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "pass"})
        token = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

async def test_create_doc(editor_client):
    r = await editor_client.post("/docs", json={
        "title": "Deploy Process",
        "path": "team/processes/deploy.md",
        "body": "# Deploy\n\nSteps here.",
        "tags": ["deployment"],
        "owner": "ed@test.com",
    })
    assert r.status_code == 201
    assert r.json()["title"] == "Deploy Process"

async def test_get_doc(editor_client):
    await editor_client.post("/docs", json={
        "title": "My Doc",
        "path": "team/processes/my-doc.md",
        "body": "content",
        "tags": [],
        "owner": "ed@test.com",
    })
    r = await editor_client.get("/docs/team/processes/my-doc.md")
    assert r.status_code == 200
    assert r.json()["title"] == "My Doc"

async def test_update_doc(editor_client):
    await editor_client.post("/docs", json={
        "title": "Old Title",
        "path": "team/processes/update-me.md",
        "body": "old body",
        "tags": [],
        "owner": "ed@test.com",
    })
    r = await editor_client.put("/docs/team/processes/update-me.md", json={"title": "New Title", "body": "new body"})
    assert r.status_code == 200
    assert r.json()["title"] == "New Title"

async def test_delete_requires_admin(editor_client):
    r = await editor_client.delete("/docs/team/processes/deploy.md")
    assert r.status_code == 403
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_docs.py -v
```
Expected: FAIL

**Step 3: Implement `api/docs_/service.py`**

```python
import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document
from config import settings
import frontmatter

async def write_doc_file(path: str, title: str, body: str, meta: dict):
    full_path = Path(settings.vault_path) / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **{"title": title, **meta})
    full_path.write_text(frontmatter.dumps(post))

async def create_doc(path: str, title: str, body: str, tags: list, owner: str, session: AsyncSession) -> Document:
    meta = {"tags": tags, "owner": owner, "status": "current"}
    await write_doc_file(path, title, body, meta)
    doc = Document(path=path, title=title, tags=json.dumps(tags), owner=owner, body_preview=body[:500])
    session.add(doc)
    await session.commit()
    return doc

async def get_doc(path: str, session: AsyncSession) -> Document | None:
    result = await session.execute(select(Document).where(Document.path == path))
    return result.scalar_one_or_none()

async def update_doc(path: str, updates: dict, session: AsyncSession) -> Document | None:
    doc = await get_doc(path, session)
    if not doc:
        return None
    for key, value in updates.items():
        setattr(doc, key, value)
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        if "title" in updates:
            post.metadata["title"] = updates["title"]
        if "body" in updates:
            post.content = updates["body"]
        full_path.write_text(frontmatter.dumps(post))
    await session.commit()
    return doc

async def delete_doc(path: str, session: AsyncSession) -> bool:
    doc = await get_doc(path, session)
    if not doc:
        return False
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        full_path.unlink()
    await session.delete(doc)
    await session.commit()
    return True
```

**Step 4: Implement `api/docs_/router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db.database import get_session
from docs_.service import create_doc, get_doc, update_doc, delete_doc
from auth.users import require_editor, require_admin, current_active_user

router = APIRouter(prefix="/docs", tags=["docs"])

class DocCreate(BaseModel):
    title: str
    path: str
    body: str
    tags: list[str] = []
    owner: str = ""

class DocUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    status: str | None = None

@router.post("", status_code=201, dependencies=[Depends(require_editor)])
async def create(payload: DocCreate, session=Depends(get_session)):
    doc = await create_doc(payload.path, payload.title, payload.body, payload.tags, payload.owner, session)
    return {"id": doc.id, "title": doc.title, "path": doc.path}

@router.get("/{path:path}")
async def read(path: str, session=Depends(get_session), user=Depends(current_active_user)):
    doc = await get_doc(path, session)
    if not doc:
        raise HTTPException(404)
    return doc

@router.put("/{path:path}", dependencies=[Depends(require_editor)])
async def update(path: str, payload: DocUpdate, session=Depends(get_session)):
    updates = payload.model_dump(exclude_none=True)
    doc = await update_doc(path, updates, session)
    if not doc:
        raise HTTPException(404)
    return doc

@router.delete("/{path:path}", dependencies=[Depends(require_admin)])
async def delete(path: str, session=Depends(get_session)):
    ok = await delete_doc(path, session)
    if not ok:
        raise HTTPException(404)
    return {"deleted": True}
```

Register router in `main.py`: `app.include_router(docs_router)`

**Step 5: Run tests to verify they pass**

```bash
cd api && pytest tests/test_docs.py -v
```
Expected: 4 PASSED

**Step 6: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 7: Commit**

```bash
git add api/docs_/ api/tests/test_docs.py api/main.py
git commit -m "feat: document CRUD API with role-based access control"
```

---

## Task 8: Search API

**Files:**
- Modify: `api/search/service.py`
- Create: `api/search/router.py`
- Modify: `api/tests/test_search.py`

**Step 1: Add keyword search test**

```python
# append to api/tests/test_search.py
async def test_keyword_search(session):
    from search.service import search_keyword
    # Pre-populate DB with a doc
    doc = Document(path="team/processes/deploy.md", title="Kubernetes Deploy", tags='["kubernetes"]', body_preview="steps to deploy")
    session.add(doc)
    await session.commit()
    results = await search_keyword("kubernetes", session)
    assert any("Kubernetes" in r["title"] for r in results)
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_search.py::test_keyword_search -v
```
Expected: FAIL

**Step 3: Implement keyword search in `api/search/service.py`**

```python
# append to search/service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from db.models import Document

async def search_keyword(query: str, session: AsyncSession) -> list[dict]:
    q = f"%{query}%"
    result = await session.execute(
        select(Document).where(
            or_(Document.title.ilike(q), Document.tags.ilike(q), Document.body_preview.ilike(q))
        )
    )
    docs = result.scalars().all()
    return [{"id": d.id, "path": d.path, "title": d.title, "tags": d.tags} for d in docs]
```

**Step 4: Create `api/search/router.py`**

```python
from fastapi import APIRouter, Depends, Query
from db.database import get_session
from search.service import search_keyword, search_semantic
from auth.users import current_active_user

router = APIRouter(prefix="/search", tags=["search"])

@router.get("")
async def search(
    q: str = Query(..., min_length=1),
    mode: str = Query("keyword", pattern="^(keyword|semantic|both)$"),
    session=Depends(get_session),
    user=Depends(current_active_user),
):
    if mode == "keyword":
        return await search_keyword(q, session)
    elif mode == "semantic":
        return await search_semantic(q)
    else:
        kw = await search_keyword(q, session)
        sem = await search_semantic(q)
        # merge, deduplicate by path
        seen = {r["path"] for r in kw}
        combined = kw + [r for r in sem if r["path"] not in seen]
        return combined
```

Register router in `main.py`: `app.include_router(search_router)`

**Step 5: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 6: Commit**

```bash
git add api/search/ api/tests/test_search.py api/main.py
git commit -m "feat: keyword and semantic search API"
```

---

## Task 9: AI Service (Auto-tagging + Staleness)

**Files:**
- Create: `api/ai/service.py`
- Create: `api/ai/__init__.py`
- Create: `api/tests/test_ai.py`

**Step 1: Write the failing tests**

```python
# api/tests/test_ai.py
import pytest
from unittest.mock import AsyncMock, patch

async def test_suggest_tags():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '["kubernetes", "deployment", "infrastructure"]'}
        ))
        from ai.service import suggest_tags
        tags = await suggest_tags("Steps to deploy to Kubernetes production cluster", existing_tags=["kubernetes", "ci-cd"])
        assert isinstance(tags, list)
        assert all(t in ["kubernetes", "deployment", "infrastructure"] for t in tags)

async def test_check_staleness():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '{"stale": true, "reason": "References Docker version 19 which is outdated"}'}
        ))
        from ai.service import check_staleness
        result = await check_staleness("Use Docker 19 to build your image...")
        assert result["stale"] is True
        assert "reason" in result
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_ai.py -v
```
Expected: FAIL

**Step 3: Implement `api/ai/service.py`**

```python
import httpx
import json
from config import settings

SYSTEM_TAGS = "You are a tagging assistant. Given document content and a list of existing tags, return a JSON array of 3-5 relevant tags chosen from or consistent with the existing tags. Return ONLY valid JSON."

SYSTEM_STALE = "You are a document staleness detector. Given document content, return a JSON object with 'stale' (boolean) and 'reason' (string). Mark as stale if you detect version numbers, tool names, or procedures that may be outdated. Return ONLY valid JSON."

async def _ollama(prompt: str, system: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": "llama3.2", "prompt": prompt, "system": system, "stream": False},
        )
        return r.json()["response"]

async def suggest_tags(body: str, existing_tags: list[str]) -> list[str]:
    prompt = f"Existing tags: {existing_tags}\n\nDocument content:\n{body[:2000]}"
    raw = await _ollama(prompt, SYSTEM_TAGS)
    return json.loads(raw)

async def check_staleness(body: str) -> dict:
    raw = await _ollama(body[:3000], SYSTEM_STALE)
    return json.loads(raw)

async def classify_ingestion_intent(message: str, candidate_paths: list[str]) -> dict:
    prompt = f"Message: {message}\n\nExisting doc paths:\n" + "\n".join(candidate_paths[:20])
    system = "Return JSON: {'action': 'create'|'update', 'path': string|null, 'title': string, 'body': string}. If updating, pick the most relevant path. If unsure, use 'create'."
    raw = await _ollama(prompt, system)
    return json.loads(raw)
```

Create `api/ai/__init__.py` (empty).

**Step 4: Run tests to verify they pass**

```bash
cd api && pytest tests/test_ai.py -v
```
Expected: 2 PASSED

**Step 5: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 6: Commit**

```bash
git add api/ai/ api/tests/test_ai.py
git commit -m "feat: AI service for auto-tagging and staleness detection via Ollama"
```

---

## Task 10: Review Queue + Scheduler

**Files:**
- Create: `api/scheduler/jobs.py`
- Create: `api/scheduler/__init__.py`
- Create: `api/review/router.py`
- Create: `api/review/__init__.py`
- Modify: `api/main.py`

**Step 1: Write the failing test**

```python
# api/tests/test_review.py
import pytest
from datetime import date, timedelta
from db.models import Document
from scheduler.jobs import get_overdue_docs
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()

async def test_overdue_docs_returned(session):
    overdue = Document(
        path="team/processes/old.md", title="Old Doc",
        last_reviewed=str(date.today() - timedelta(days=60)),
        review_interval="30d", status="current"
    )
    current = Document(
        path="team/processes/new.md", title="New Doc",
        last_reviewed=str(date.today() - timedelta(days=5)),
        review_interval="30d", status="current"
    )
    session.add_all([overdue, current])
    await session.commit()
    results = await get_overdue_docs(session)
    paths = [r.path for r in results]
    assert "team/processes/old.md" in paths
    assert "team/processes/new.md" not in paths
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_review.py -v
```
Expected: FAIL

**Step 3: Implement `api/scheduler/jobs.py`**

```python
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document

def _parse_interval(interval: str) -> int:
    """Convert '30d' to 30, '90d' to 90."""
    return int(interval.rstrip("d"))

async def get_overdue_docs(session: AsyncSession) -> list[Document]:
    result = await session.execute(select(Document).where(Document.last_reviewed.isnot(None)))
    docs = result.scalars().all()
    overdue = []
    for doc in docs:
        try:
            reviewed = date.fromisoformat(doc.last_reviewed)
            interval = _parse_interval(doc.review_interval or "90d")
            if (date.today() - reviewed).days >= interval:
                overdue.append(doc)
        except (ValueError, TypeError):
            pass
    return overdue

async def run_staleness_check():
    """Called nightly by APScheduler."""
    from db.database import async_session_maker
    from ai.service import check_staleness
    from pathlib import Path
    from config import settings
    async with async_session_maker() as session:
        docs = await get_overdue_docs(session)
        for doc in docs:
            path = Path(settings.vault_path) / doc.path
            if not path.exists():
                continue
            body = path.read_text()
            result = await check_staleness(body)
            if result.get("stale"):
                doc.status = "needs_review"
                await session.commit()
```

Create `api/scheduler/__init__.py` (empty).

**Step 4: Wire APScheduler into `main.py` lifespan**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from scheduler.jobs import run_staleness_check

scheduler = AsyncIOScheduler()

# inside lifespan, before yield:
scheduler.add_job(run_staleness_check, "cron", hour=2)  # 2am nightly
scheduler.start()

# after yield:
scheduler.shutdown()
```

**Step 5: Create `api/review/router.py`**

```python
from fastapi import APIRouter, Depends
from db.database import get_session
from scheduler.jobs import get_overdue_docs
from auth.users import current_active_user

router = APIRouter(prefix="/review", tags=["review"])

@router.get("/queue")
async def queue(session=Depends(get_session), user=Depends(current_active_user)):
    docs = await get_overdue_docs(session)
    return [{"id": d.id, "path": d.path, "title": d.title, "last_reviewed": d.last_reviewed} for d in docs]

@router.post("/{doc_id}/mark-reviewed", dependencies=[Depends(current_active_user)])
async def mark_reviewed(doc_id: int, session=Depends(get_session)):
    from sqlalchemy import select
    from db.models import Document
    from datetime import date
    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc:
        doc.last_reviewed = str(date.today())
        doc.status = "current"
        await session.commit()
    return {"marked_reviewed": True}
```

Register router in `main.py`.

**Step 6: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 7: Commit**

```bash
git add api/scheduler/ api/review/ api/tests/test_review.py api/main.py
git commit -m "feat: review queue, staleness scheduler, mark-reviewed endpoint"
```

---

## Task 11: Ingestion Service

**Files:**
- Create: `api/ingestion/service.py`
- Create: `api/ingestion/router.py`
- Create: `api/ingestion/__init__.py`
- Create: `api/tests/test_ingestion.py`

**Step 1: Write the failing test**

```python
# api/tests/test_ingestion.py
import pytest
from unittest.mock import AsyncMock, patch

async def test_ingest_creates_new_doc():
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "team/processes/new-process.md",
        "title": "New Process",
        "body": "Steps for the new process.",
    })):
        with patch("ingestion.service.create_doc", new=AsyncMock(return_value=None)):
            from ingestion.service import ingest_message
            result = await ingest_message("We have a new onboarding process: ...", session=AsyncMock())
            assert result["action"] == "create"
            assert "new-process" in result["path"]

async def test_ingest_updates_existing_doc():
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update",
        "path": "team/processes/deploy.md",
        "title": "Deploy Process",
        "body": "Updated deploy steps.",
    })):
        with patch("ingestion.service.update_doc", new=AsyncMock(return_value=AsyncMock())):
            from ingestion.service import ingest_message
            result = await ingest_message("Update the deploy doc: now use Docker 24", session=AsyncMock())
            assert result["action"] == "update"
```

**Step 2: Run to verify failure**

```bash
cd api && pytest tests/test_ingestion.py -v
```
Expected: FAIL

**Step 3: Implement `api/ingestion/service.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document
from ai.service import classify_ingestion_intent
from docs_.service import create_doc, update_doc

async def ingest_message(message: str, session: AsyncSession) -> dict:
    # Get existing doc paths for context
    result = await session.execute(select(Document.path))
    paths = [r[0] for r in result.fetchall()]

    intent = await classify_ingestion_intent(message, paths)
    action = intent.get("action", "create")
    path = intent.get("path", "")
    title = intent.get("title", "Untitled")
    body = intent.get("body", message)

    if action == "update" and path:
        await update_doc(path, {"title": title, "body": body}, session)
        return {"action": "update", "path": path, "message": f"Updated doc: {title}. Done."}
    else:
        if not path:
            slug = title.lower().replace(" ", "-")[:40]
            path = f"team/processes/{slug}.md"
        await create_doc(path, title, body, [], "", session)
        return {"action": "create", "path": path, "message": f"Created doc: {title}. Done."}
```

**Step 4: Create `api/ingestion/router.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from db.database import get_session
from ingestion.service import ingest_message
from auth.users import current_active_user

router = APIRouter(prefix="/ingest", tags=["ingestion"])

class IngestPayload(BaseModel):
    message: str
    reply_to: str = ""  # email/chat address to reply to (platform TBD)

@router.post("")
async def ingest(payload: IngestPayload, session=Depends(get_session), user=Depends(current_active_user)):
    result = await ingest_message(payload.message, session)
    return result
```

Register router in `main.py`.

**Step 5: Run all tests**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 6: Commit**

```bash
git add api/ingestion/ api/tests/test_ingestion.py api/main.py
git commit -m "feat: ingestion service — AI-driven create/update from free-text messages"
```

---

## Task 12: React Frontend Scaffold

**Files:**
- Create: `ui/package.json`
- Create: `ui/vite.config.ts`
- Create: `ui/index.html`
- Create: `ui/src/main.tsx`
- Create: `ui/src/App.tsx`
- Create: `ui/src/api/client.ts`
- Create: `ui/Dockerfile`
- Create: `ui/nginx.conf`

**Step 1: Initialize React + Vite project**

```bash
cd ui && npm create vite@latest . -- --template react-ts
npm install
npm install @codemirror/view @codemirror/state @codemirror/lang-markdown
npm install marked react-router-dom
```

**Step 2: Create `ui/src/api/client.ts`**

```typescript
const BASE = import.meta.env.VITE_API_URL ?? "/api";

async function request(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  login: (email: string, password: string) =>
    fetch(`${BASE}/auth/jwt/login`, {
      method: "POST",
      body: new URLSearchParams({ username: email, password }),
    }).then(r => r.json()),

  getDoc: (path: string) => request(`/docs/${path}`),
  createDoc: (data: object) => request("/docs", { method: "POST", body: JSON.stringify(data) }),
  updateDoc: (path: string, data: object) => request(`/docs/${path}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteDoc: (path: string) => request(`/docs/${path}`, { method: "DELETE" }),
  search: (q: string, mode = "both") => request(`/search?q=${encodeURIComponent(q)}&mode=${mode}`),
  reviewQueue: () => request("/review/queue"),
  markReviewed: (id: number) => request(`/review/${id}/mark-reviewed`, { method: "POST" }),
};
```

**Step 3: Create `ui/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Home from "./pages/Home";
import DocPage from "./pages/DocPage";
import ReviewPage from "./pages/ReviewPage";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return localStorage.getItem("token") ? <>{children}</> : <Navigate to="/login" />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<PrivateRoute><Home /></PrivateRoute>} />
        <Route path="/doc/*" element={<PrivateRoute><DocPage /></PrivateRoute>} />
        <Route path="/review" element={<PrivateRoute><ReviewPage /></PrivateRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
```

**Step 4: Create `ui/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

**Step 5: Create `ui/nginx.conf`**

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;
  location / { try_files $uri $uri/ /index.html; }
  location /api { proxy_pass http://api:8000; }
}
```

**Step 6: Verify UI builds**

```bash
cd ui && npm run build
```
Expected: `dist/` directory created, no errors.

**Step 7: Commit**

```bash
git add ui/
git commit -m "feat: React + Vite frontend scaffold with routing and API client"
```

---

## Task 13: Login Page

**Files:**
- Create: `ui/src/pages/Login.tsx`

**Step 1: Implement `ui/src/pages/Login.tsx`**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const data = await api.login(email, password);
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
        navigate("/");
      } else {
        setError("Invalid credentials");
      }
    } catch {
      setError("Login failed");
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: "100px auto", padding: 24 }}>
      <h1>Knowledge Base</h1>
      <form onSubmit={submit}>
        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required style={{ display: "block", width: "100%", marginBottom: 8 }} />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required style={{ display: "block", width: "100%", marginBottom: 8 }} />
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit" style={{ width: "100%" }}>Log in</button>
      </form>
    </div>
  );
}
```

**Step 2: Verify it renders**

```bash
cd ui && npm run dev
```
Navigate to `http://localhost:5173/login` — login form should render.

**Step 3: Commit**

```bash
git add ui/src/pages/Login.tsx
git commit -m "feat: login page"
```

---

## Task 14: Home Page (Search)

**Files:**
- Create: `ui/src/pages/Home.tsx`
- Create: `ui/src/components/SearchBar.tsx`

**Step 1: Implement `ui/src/components/SearchBar.tsx`**

```tsx
import { useState } from "react";

interface Props {
  onSearch: (query: string) => void;
}

export default function SearchBar({ onSearch }: Props) {
  const [query, setQuery] = useState("");
  return (
    <form onSubmit={e => { e.preventDefault(); onSearch(query); }} style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search docs..." style={{ flex: 1, padding: 8 }} />
      <button type="submit">Search</button>
    </form>
  );
}
```

**Step 2: Implement `ui/src/pages/Home.tsx`**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import SearchBar from "../components/SearchBar";

interface DocResult { id: number; path: string; title: string; }

export default function Home() {
  const [results, setResults] = useState<DocResult[]>([]);
  const navigate = useNavigate();

  async function handleSearch(q: string) {
    if (!q.trim()) return;
    const data = await api.search(q);
    setResults(data);
  }

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Knowledge Base</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => navigate("/doc/new")}>+ New Doc</button>
          <button onClick={() => navigate("/review")}>Review Queue</button>
        </div>
      </div>
      <SearchBar onSearch={handleSearch} />
      <ul style={{ listStyle: "none", padding: 0 }}>
        {results.map(r => (
          <li key={r.id} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
            <a href={`/doc/${r.path}`} style={{ textDecoration: "none" }}>{r.title || r.path}</a>
            <span style={{ color: "#888", fontSize: 12, marginLeft: 8 }}>{r.path}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

**Step 3: Verify in browser**

```bash
cd ui && npm run dev
```
Log in, confirm search bar and results list render on home page.

**Step 4: Commit**

```bash
git add ui/src/pages/Home.tsx ui/src/components/SearchBar.tsx
git commit -m "feat: home page with search"
```

---

## Task 15: Document View + Editor

**Files:**
- Create: `ui/src/pages/DocPage.tsx`
- Create: `ui/src/components/Editor.tsx`
- Create: `ui/src/components/DocViewer.tsx`

**Step 1: Implement `ui/src/components/DocViewer.tsx`**

```tsx
import { marked } from "marked";

interface Props { body: string; title: string; }

export default function DocViewer({ body, title }: Props) {
  return (
    <div>
      <h1>{title}</h1>
      <div dangerouslySetInnerHTML={{ __html: marked(body) }} />
    </div>
  );
}
```

**Step 2: Implement `ui/src/components/Editor.tsx`**

```tsx
import { useEffect, useRef } from "react";
import { EditorView, basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";

interface Props {
  value: string;
  onChange: (val: string) => void;
}

export default function Editor({ value, onChange }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    view.current = new EditorView({
      doc: value,
      extensions: [basicSetup, markdown(), EditorView.updateListener.of(u => {
        if (u.docChanged) onChange(u.state.doc.toString());
      })],
      parent: ref.current,
    });
    return () => view.current?.destroy();
  }, []);

  return <div ref={ref} style={{ border: "1px solid #ccc", minHeight: 400 }} />;
}
```

**Step 3: Implement `ui/src/pages/DocPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import DocViewer from "../components/DocViewer";
import Editor from "../components/Editor";

export default function DocPage() {
  const { "*": path } = useParams();
  const navigate = useNavigate();
  const isNew = path === "new";
  const [doc, setDoc] = useState({ title: "", body: "", path: "" });
  const [editing, setEditing] = useState(isNew);

  useEffect(() => {
    if (!isNew && path) api.getDoc(path).then(setDoc);
  }, [path]);

  async function save() {
    if (isNew) {
      await api.createDoc({ title: doc.title, path: doc.path, body: doc.body, tags: [] });
      navigate(`/doc/${doc.path}`);
    } else {
      await api.updateDoc(path!, { title: doc.title, body: doc.body });
      setEditing(false);
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!editing && <button onClick={() => setEditing(true)}>Edit</button>}
        {editing && <button onClick={save}>Save</button>}
        {editing && !isNew && <button onClick={() => setEditing(false)}>Cancel</button>}
      </div>
      {editing ? (
        <>
          <input value={doc.title} onChange={e => setDoc(d => ({ ...d, title: e.target.value }))} placeholder="Title" style={{ display: "block", width: "100%", fontSize: 24, marginBottom: 8 }} />
          {isNew && <input value={doc.path} onChange={e => setDoc(d => ({ ...d, path: e.target.value }))} placeholder="Path (e.g. team/processes/deploy.md)" style={{ display: "block", width: "100%", marginBottom: 8 }} />}
          <Editor value={doc.body} onChange={body => setDoc(d => ({ ...d, body }))} />
        </>
      ) : (
        <DocViewer title={doc.title} body={doc.body} />
      )}
    </div>
  );
}
```

**Step 4: Verify in browser**

Navigate to an existing doc and a new doc. Confirm view/edit toggle, CodeMirror editor renders, save works.

**Step 5: Commit**

```bash
git add ui/src/pages/DocPage.tsx ui/src/components/
git commit -m "feat: document view and in-browser markdown editor"
```

---

## Task 16: Review Queue UI

**Files:**
- Create: `ui/src/pages/ReviewPage.tsx`
- Create: `ui/src/components/ReviewQueue.tsx`

**Step 1: Implement `ui/src/components/ReviewQueue.tsx`**

```tsx
import { api } from "../api/client";

interface Doc { id: number; path: string; title: string; last_reviewed: string; }
interface Props { docs: Doc[]; onMarked: (id: number) => void; }

export default function ReviewQueue({ docs, onMarked }: Props) {
  if (docs.length === 0) return <p>No docs need review.</p>;
  return (
    <ul style={{ listStyle: "none", padding: 0 }}>
      {docs.map(d => (
        <li key={d.id} style={{ borderBottom: "1px solid #eee", padding: "12px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <a href={`/doc/${d.path}`}>{d.title || d.path}</a>
            <div style={{ color: "#888", fontSize: 12 }}>Last reviewed: {d.last_reviewed || "never"}</div>
          </div>
          <button onClick={() => api.markReviewed(d.id).then(() => onMarked(d.id))}>
            Mark reviewed
          </button>
        </li>
      ))}
    </ul>
  );
}
```

**Step 2: Implement `ui/src/pages/ReviewPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ReviewQueue from "../components/ReviewQueue";

export default function ReviewPage() {
  const [docs, setDocs] = useState([]);
  const navigate = useNavigate();

  useEffect(() => { api.reviewQueue().then(setDocs); }, []);

  function handleMarked(id: number) {
    setDocs(d => d.filter((doc: any) => doc.id !== id));
  }

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <button onClick={() => navigate("/")}>← Back</button>
      <h1>Review Queue</h1>
      <ReviewQueue docs={docs} onMarked={handleMarked} />
    </div>
  );
}
```

**Step 3: Verify in browser**

Navigate to `/review` — queue renders, "Mark reviewed" removes item from list.

**Step 4: Commit**

```bash
git add ui/src/pages/ReviewPage.tsx ui/src/components/ReviewQueue.tsx
git commit -m "feat: review queue UI with mark-reviewed"
```

---

## Task 17: Caddy + End-to-End Smoke Test

**Files:**
- Create: `caddy/Caddyfile`

**Step 1: Create `caddy/Caddyfile`**

```
:80 {
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy api:8000
    }
    handle {
        reverse_proxy ui:80
    }
}
```

**Step 2: Pull Ollama models**

```bash
docker compose up ollama -d
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text
```

**Step 3: Start the full stack**

```bash
cp .env.example .env
docker compose up --build
```

**Step 4: Smoke test checklist**

- [ ] `http://localhost` loads the login page
- [ ] Register a user, log in, redirected to home
- [ ] Create a new doc, verify it appears in `vault/`
- [ ] Edit the doc, verify file is updated
- [ ] Search for the doc by title — appears in results
- [ ] Navigate to `/review` — queue renders
- [ ] `GET http://localhost/api/health` returns `{"status": "ok"}`

**Step 5: Run full backend test suite one final time**

```bash
cd api && pytest -v
```
Expected: All PASSED

**Step 6: Final commit**

```bash
git add caddy/
git commit -m "feat: Caddy reverse proxy config and full stack integration"
```

---

## Notes for Implementer

- **Ollama cold start:** First AI call will be slow while the model loads. Subsequent calls are fast.
- **ChromaDB + SQLite:** Both indexes are fully disposable. Delete `/data` volume and restart to rebuild from vault files.
- **Ingestion platform:** The `/ingest` API endpoint is platform-agnostic. A future task will add an email (IMAP) or chat adapter on top of it — design is intentionally decoupled.
- **Frontend styling:** Deliberately minimal (inline styles). Add a CSS framework (e.g. Tailwind) in a follow-up task if desired.
- **fastapi-users setup:** Follow the official async SQLAlchemy guide exactly — it's detailed and the implementation skeleton in Task 6 is intentionally simplified.
