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
