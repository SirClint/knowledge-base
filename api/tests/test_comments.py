import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine
from main import app


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    import db.database as _db
    from db.database import create_db
    from db.models import Base

    # Wipe and recreate schema for a clean slate (conftest resets engine ref but not data)
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:////tmp/test.db")
    tmp_engine = create_async_engine(db_url)
    async with tmp_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await tmp_engine.dispose()
    _db._engine = None
    _db._maker = None
    await create_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/register", json={"email": "ed@test.com", "password": "pass", "role": "editor"})
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "pass"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
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

    await editor_client.post("/auth/register", json={"email": "r@test.com", "password": "pass", "role": "reader"})
    login = await editor_client.post("/auth/jwt/login", data={"username": "r@test.com", "password": "pass"})
    reader_token = login.json()["access_token"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as rc:
        rc.headers["Authorization"] = f"Bearer {reader_token}"
        r = await rc.delete(f"/comments/{comment_id}")
        assert r.status_code == 403


async def test_comment_body_max_length(editor_client):
    r = await editor_client.post("/comments/personal/commented.md", json={"body": "x" * 2001})
    assert r.status_code == 400


async def test_comment_body_whitespace_only(editor_client):
    r = await editor_client.post("/comments/personal/commented.md", json={"body": "   "})
    assert r.status_code == 400
