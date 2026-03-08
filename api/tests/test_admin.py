import pytest
from httpx import AsyncClient, ASGITransport
from main import app


async def _make_client_with_role(role: str):
    """Helper: returns (client, token) for a registered user with given role."""
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    email = f"{role}@test.com"
    await c.post("/auth/register", json={"email": email, "password": "pass", "role": role})
    r = await c.post("/auth/jwt/login", data={"username": email, "password": "pass"})
    token = r.json()["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c


@pytest.fixture
async def admin_client():
    c = await _make_client_with_role("admin")
    yield c
    await c.aclose()


@pytest.fixture
async def reader_client():
    c = await _make_client_with_role("reader")
    yield c
    await c.aclose()


async def test_list_users_as_admin(admin_client):
    r = await admin_client.get("/admin/users")
    assert r.status_code == 200
    users = r.json()
    assert isinstance(users, list)
    assert any(u["email"] == "admin@test.com" for u in users)


async def test_list_users_forbidden_for_reader(reader_client):
    r = await reader_client.get("/admin/users")
    assert r.status_code == 403


async def test_change_role(admin_client):
    # Register a target user
    await admin_client.post("/auth/register", json={"email": "target@test.com", "password": "pass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "target@test.com")
    r = await admin_client.patch(f"/admin/users/{target['id']}/role", json={"role": "editor"})
    assert r.status_code == 200
    assert r.json()["role"] == "editor"


async def test_reset_password(admin_client):
    await admin_client.post("/auth/register", json={"email": "reset@test.com", "password": "oldpass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "reset@test.com")
    r = await admin_client.post(f"/admin/users/{target['id']}/reset-password", json={"password": "newpass123"})
    assert r.status_code == 200
    # Verify new password works
    login = await admin_client.post("/auth/jwt/login", data={"username": "reset@test.com", "password": "newpass123"})
    assert "access_token" in login.json()


async def test_delete_user(admin_client):
    await admin_client.post("/auth/register", json={"email": "todelete@test.com", "password": "pass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "todelete@test.com")
    r = await admin_client.delete(f"/admin/users/{target['id']}")
    assert r.status_code == 204
    users_after = (await admin_client.get("/admin/users")).json()
    assert not any(u["email"] == "todelete@test.com" for u in users_after)


async def test_cannot_delete_own_account(admin_client):
    users = (await admin_client.get("/admin/users")).json()
    self_user = next(u for u in users if u["email"] == "admin@test.com")
    r = await admin_client.delete(f"/admin/users/{self_user['id']}")
    assert r.status_code == 400


async def test_change_role_invalid_value(admin_client):
    await admin_client.post("/auth/register", json={"email": "target2@test.com", "password": "pass", "role": "reader"})
    users = (await admin_client.get("/admin/users")).json()
    target = next(u for u in users if u["email"] == "target2@test.com")
    r = await admin_client.patch(f"/admin/users/{target['id']}/role", json={"role": "superuser"})
    assert r.status_code == 400


async def test_reset_password_forbidden_for_reader(reader_client):
    r = await reader_client.post("/admin/users/00000000-0000-0000-0000-000000000000/reset-password", json={"password": "newpass123"})
    assert r.status_code == 403
