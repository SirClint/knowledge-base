import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


async def _upsert_user(email: str, password: str, role: str) -> None:
    """Delete any existing user with this email then recreate with the specified role/password."""
    import auth.users  # noqa: F401
    from db.database import async_session_maker
    from auth.users import User
    from sqlalchemy import delete
    async with async_session_maker() as session:
        await session.execute(delete(User).where(User.email == email))
        await session.commit()
    await create_test_user(email, password, role)


@pytest.fixture
async def admin_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    await _upsert_user("admin@test.com", "Securepass1!", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "admin@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


@pytest.fixture
async def reader_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    await _upsert_user("reader@test.com", "Securepass1!", "reader")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "reader@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


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


# ── Settings ──────────────────────────────────────────────────────────────────

async def test_get_settings_returns_default_threshold(admin_client):
    r = await admin_client.get("/admin/settings")
    assert r.status_code == 200
    data = r.json()
    assert "semantic_threshold" in data
    assert float(data["semantic_threshold"]) == 0.50


async def test_get_settings_forbidden_for_reader(reader_client):
    r = await reader_client.get("/admin/settings")
    assert r.status_code == 403


async def test_update_setting_valid_value(admin_client):
    r = await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "0.75"})
    assert r.status_code == 200
    assert r.json() == {"key": "semantic_threshold", "value": "0.75"}


async def test_update_setting_persists(admin_client):
    await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "0.65"})
    r = await admin_client.get("/admin/settings")
    assert r.json()["semantic_threshold"] == "0.65"


async def test_update_setting_boundary_zero(admin_client):
    r = await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "0.0"})
    assert r.status_code == 200


async def test_update_setting_boundary_one(admin_client):
    r = await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "1.0"})
    assert r.status_code == 200


async def test_update_setting_above_one_rejected(admin_client):
    r = await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "1.01"})
    assert r.status_code == 400
    assert "0.0" in r.json()["detail"] and "1.0" in r.json()["detail"]


async def test_update_setting_negative_rejected(admin_client):
    r = await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "-0.01"})
    assert r.status_code == 400


async def test_update_setting_non_numeric_rejected(admin_client):
    r = await admin_client.patch("/admin/settings/semantic_threshold", json={"value": "banana"})
    assert r.status_code == 400


async def test_update_unknown_setting_rejected(admin_client):
    r = await admin_client.patch("/admin/settings/unknown_key", json={"value": "anything"})
    assert r.status_code == 400
    assert "Unknown setting" in r.json()["detail"]


async def test_update_setting_forbidden_for_reader(reader_client):
    r = await reader_client.patch("/admin/settings/semantic_threshold", json={"value": "0.9"})
    assert r.status_code == 403
