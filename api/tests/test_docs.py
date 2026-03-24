import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def editor_client():
    import auth.users  # noqa: F401
    from db.database import create_db
    from db.database import async_session_maker
    from auth.users import User
    from sqlalchemy import delete
    await create_db()
    # Remove any stale user so create_test_user always inserts fresh with the correct password/role
    async with async_session_maker() as session:
        await session.execute(delete(User).where(User.email == "ed@test.com"))
        await session.commit()
    await create_test_user("ed@test.com", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "ed@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
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


async def test_list_docs(editor_client):
    # Create two docs in different folders (unique paths to avoid UNIQUE constraint conflicts)
    await editor_client.post("/docs", json={
        "title": "Personal Note",
        "path": "personal/list-test-note.md",
        "body": "content",
        "tags": [],
        "owner": "ed@test.com",
    })
    await editor_client.post("/docs", json={
        "title": "List Deploy Process",
        "path": "team/processes/list-test-deploy.md",
        "body": "steps",
        "tags": [],
        "owner": "ed@test.com",
    })
    r = await editor_client.get("/docs")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    paths = [d["path"] for d in data]
    assert "personal/list-test-note.md" in paths
    assert "team/processes/list-test-deploy.md" in paths
    for d in data:
        assert "id" in d
        assert "path" in d
        assert "title" in d


async def test_doc_get_includes_metadata(editor_client):
    await editor_client.post("/docs", json={
        "title": "Meta Test Doc",
        "path": "personal/meta-create-test.md",
        "body": "some body",
        "tags": [],
        "owner": "ed@test.com",
    })
    r = await editor_client.get("/docs/personal/meta-create-test.md")
    assert r.status_code == 200
    data = r.json()
    assert data["created_at"] is not None, "created_at should be set on creation"
    assert data["created_by"] == "ed@test.com", "created_by should equal owner"
    assert data["updated_at"] is not None, "updated_at should be present"
    assert not data["updated_by"], "updated_by should be empty on fresh create"


async def test_doc_update_sets_updated_by(editor_client):
    await editor_client.post("/docs", json={
        "title": "Update Meta Doc",
        "path": "personal/meta-update-test.md",
        "body": "original",
        "tags": [],
        "owner": "ed@test.com",
    })
    await editor_client.put("/docs/personal/meta-update-test.md", json={"title": "Updated Title"})
    r = await editor_client.get("/docs/personal/meta-update-test.md")
    assert r.status_code == 200
    data = r.json()
    assert data["updated_by"] == "ed@test.com", "updated_by should equal editor email after save"
