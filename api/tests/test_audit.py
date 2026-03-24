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
    import auth.users  # noqa
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import delete
    await create_db()
    async with async_session_maker() as session:
        await session.execute(delete(User).where(User.email == "ed@audit.test"))
        await session.commit()
    await create_test_user("ed@audit.test", "Securepass1!", "editor")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "ed@audit.test", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_doc_create_logged(editor_client):
    """Creating a document writes a doc.create audit event."""
    from db.database import async_session_maker
    from db.models import AuditLog
    from sqlalchemy import select

    await editor_client.post("/docs", json={
        "title": "Audit Test Doc",
        "path": "team/audit-test.md",
        "body": "content",
        "tags": [],
    })

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "doc.create")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.target == "team/audit-test.md"


async def test_login_success_logged(client):
    """Successful login writes an auth.login_success audit event."""
    from db.database import async_session_maker, create_db
    from db.models import AuditLog
    from sqlalchemy import select
    from tests.conftest import create_test_user
    import auth.users  # noqa

    await create_db()
    await create_test_user("logintest@test.com", "Securepass1!", "reader")
    await client.post("/auth/jwt/login", data={
        "username": "logintest@test.com",
        "password": "Securepass1!",
    })

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.action == "auth.login_success",
                AuditLog.actor_email == "logintest@test.com",
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None


async def test_log_event_writes_to_db(editor_client):
    """log_event() creates an AuditLog row in the database."""
    from db.database import async_session_maker
    from db.models import AuditLog
    from audit.service import log_event
    from sqlalchemy import select

    async with async_session_maker() as session:
        await log_event(session, actor_email="test@test.com", action="test.event", target="some/doc.md")

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "test.event")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.actor_email == "test@test.com"
        assert row.target == "some/doc.md"


async def test_login_failure_logged(client):
    """Failed login attempt writes an auth.login_failure audit event."""
    from db.database import async_session_maker, create_db
    from db.models import AuditLog
    from sqlalchemy import select
    import auth.users  # noqa

    await create_db()
    await client.post("/auth/jwt/login", data={
        "username": "nonexistent@example.com",
        "password": "wrongpassword",
    })

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "auth.login_failure")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.actor_email == "nonexistent@example.com"


async def test_admin_audit_log_endpoint(editor_client):
    """GET /admin/audit-log returns audit events (admin only)."""
    from tests.conftest import create_test_user
    from db.database import create_db
    import auth.users  # noqa
    from httpx import AsyncClient, ASGITransport
    from main import app

    await create_db()
    await create_test_user("audit_admin@test.com", "Securepass1!", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "audit_admin@test.com", "password": "Securepass1!"})
        token = r.json()["access_token"]
        r = await c.get("/admin/audit-log", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data


async def test_admin_audit_log_requires_admin(editor_client):
    """Non-admin users cannot access /admin/audit-log."""
    r = await editor_client.get("/admin/audit-log")
    assert r.status_code == 403
