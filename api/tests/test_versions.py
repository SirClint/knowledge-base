import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import delete
    await create_db()
    # Remove any stale user so we always have a fresh editor with the correct password
    async with async_session_maker() as session:
        await session.execute(delete(User).where(User.email == "ed@test.com"))
        await session.commit()
    await create_test_user("ed@test.com", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_save_creates_version(editor_client):
    # Create a doc
    await editor_client.post("/docs", json={
        "title": "My Doc", "path": "personal/ver-test.md",
        "body": "original body", "tags": [],
    })
    # Update it — should snapshot the original body
    await editor_client.put("/docs/personal/ver-test.md", json={"body": "updated body"})
    # List versions
    r = await editor_client.get("/versions/personal/ver-test.md")
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 1
    assert versions[0]["saved_by"] == "ed@test.com"


async def test_restore_version(editor_client):
    await editor_client.post("/docs", json={
        "title": "Restore Doc", "path": "personal/restore-test.md",
        "body": "v1 body", "tags": [],
    })
    await editor_client.put("/docs/personal/restore-test.md", json={"body": "v2 body"})
    versions = (await editor_client.get("/versions/personal/restore-test.md")).json()
    version_id = versions[0]["id"]

    # Restore to v1
    r = await editor_client.post(f"/versions/personal/restore-test.md/restore/{version_id}")
    assert r.status_code == 200

    # Verify doc body is back to v1
    doc = (await editor_client.get("/docs/personal/restore-test.md")).json()
    assert doc["body"] == "v1 body"


async def test_list_versions_reader_can_view(editor_client):
    await editor_client.post("/docs", json={
        "title": "Reader Doc", "path": "personal/reader-ver.md",
        "body": "body", "tags": [],
    })
    await editor_client.put("/docs/personal/reader-ver.md", json={"body": "updated"})

    # Register a reader and use their token
    await editor_client.post("/auth/register", json={"email": "r@test.com", "password": "pass", "role": "reader"})
    r = await editor_client.post("/auth/jwt/login", data={"username": "r@test.com", "password": "pass"})
    reader_token = r.json()["access_token"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as rc:
        rc.headers["Authorization"] = f"Bearer {reader_token}"
        r = await rc.get("/versions/personal/reader-ver.md")
        assert r.status_code == 200


async def test_pruning_keeps_50_versions(editor_client):
    await editor_client.post("/docs", json={
        "title": "Prune Doc", "path": "personal/prune-test.md",
        "body": "v0", "tags": [],
    })
    # Create 55 versions
    for i in range(1, 56):
        await editor_client.put("/docs/personal/prune-test.md", json={"body": f"v{i}"})
    versions = (await editor_client.get("/versions/personal/prune-test.md")).json()
    assert len(versions) == 50
