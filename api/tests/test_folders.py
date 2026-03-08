import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def auth_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/register", json={"email": "u@test.com", "password": "pass", "role": "reader"})
        r = await c.post("/auth/jwt/login", data={"username": "u@test.com", "password": "pass"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_get_folders(auth_client):
    r = await auth_client.get("/docs/folders")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert "personal" in data
    assert "team/processes" in data
