import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def editor_client():
    try:
        await create_test_user("editor@test.com", "Securepass1!", "editor")
    except Exception:
        pass  # User may already exist
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "editor@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_summary_returns_expected_fields(editor_client):
    r = await editor_client.get("/health/summary")
    assert r.status_code == 200
    data = r.json()
    assert "app_version" in data
    assert "doc_count" in data
    assert "user_count" in data
    assert "review_queue_count" in data
    assert "ai" in data
    assert data["ai"] in ("online", "offline")


async def test_summary_counts_are_integers(editor_client):
    r = await editor_client.get("/health/summary")
    data = r.json()
    assert isinstance(data["doc_count"], int)
    assert isinstance(data["user_count"], int)
    assert isinstance(data["review_queue_count"], int)


async def test_summary_counts_reflect_data(editor_client):
    # Register a user and create a doc — counts should increase
    await editor_client.post("/auth/register", json={"email": "u@test.com", "password": "pass", "role": "editor"})
    login = await editor_client.post("/auth/jwt/login", data={"username": "u@test.com", "password": "pass"})
    token = login.json()["access_token"]
    await editor_client.post("/docs",
        json={"title": "T", "path": "personal/t.md", "body": "b", "tags": []},
        headers={"Authorization": f"Bearer {token}"}
    )
    r = await editor_client.get("/health/summary")
    data = r.json()
    assert data["doc_count"] >= 1
    assert data["user_count"] >= 1


async def test_summary_requires_auth(client):
    """Summary endpoint now requires authentication."""
    r = await client.get("/health/summary")
    assert r.status_code == 401


async def test_summary_app_version_from_env(editor_client):
    from unittest.mock import patch
    with patch("config.settings.app_version", "abc1234"):
        r = await editor_client.get("/health/summary")
    assert r.json()["app_version"] == "abc1234"
