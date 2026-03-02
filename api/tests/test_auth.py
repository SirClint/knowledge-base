import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    # Import User model so it's registered with Base.metadata before create_db
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
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
        json={"title": "Test", "body": "content", "path": "team/test.md", "tags": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
