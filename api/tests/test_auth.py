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


async def test_register_as_admin_gets_reader(client):
    """Submitting role=admin at registration must produce a reader."""
    r = await client.post("/auth/register", json={
        "email": "wannabe_admin@example.com",
        "password": "Securepass1!",
        "role": "admin",
    })
    assert r.status_code == 201

    # Confirm the DB row has role='reader', not the submitted role
    from db.database import async_session_maker
    from auth.users import User
    from sqlalchemy import select
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "wannabe_admin@example.com"))
        db_user = result.scalar_one()
        assert db_user.role == "reader", f"Expected role=reader, got {db_user.role!r}"

    login = await client.post("/auth/jwt/login", data={
        "username": "wannabe_admin@example.com",
        "password": "Securepass1!",
    })
    token = login.json()["access_token"]

    # Try an admin action — must fail with 403
    r = await client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_register_as_editor_gets_reader(client):
    """Submitting role=editor at registration must produce a reader."""
    r = await client.post("/auth/register", json={
        "email": "wannabe_editor@example.com",
        "password": "Securepass1!",
        "role": "editor",
    })
    assert r.status_code == 201

    login = await client.post("/auth/jwt/login", data={
        "username": "wannabe_editor@example.com",
        "password": "Securepass1!",
    })
    token = login.json()["access_token"]

    # Try an editor action — must fail with 403
    r = await client.post("/docs", json={"title": "T", "path": "x.md", "body": "b", "tags": []},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
