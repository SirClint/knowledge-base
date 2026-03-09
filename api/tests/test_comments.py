import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    from db.database import _get_engine
    from db.models import Base
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
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
