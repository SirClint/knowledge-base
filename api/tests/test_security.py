import pytest
import importlib
from httpx import AsyncClient, ASGITransport
from main import app
from tests.conftest import create_test_user


def test_weak_secret_key_raises_on_startup(monkeypatch):
    """Settings should refuse to construct with a short or default SECRET_KEY."""
    monkeypatch.setenv("SECRET_KEY", "tooshort")
    import config
    with pytest.raises((ValueError, RuntimeError)):
        importlib.reload(config)


def test_changeme_secret_key_raises_on_startup(monkeypatch):
    """Settings should reject 'changeme' as SECRET_KEY."""
    monkeypatch.setenv("SECRET_KEY", "changeme")
    import config
    with pytest.raises((ValueError, RuntimeError)):
        importlib.reload(config)


@pytest.fixture
async def client():
    """Unauthenticated client for testing CORS and other public endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def editor_client():
    try:
        await create_test_user("editor@test.com", "Securepass1!", "editor")
    except Exception:
        pass  # User may already exist from a previous test in the same session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/jwt/login", data={"username": "editor@test.com", "password": "Securepass1!"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_path_traversal_get_blocked(editor_client):
    """GET with path traversal must return 400, not read a file outside vault.

    Uses percent-encoded dots (%2e) so the traversal survives HTTPX URL
    normalization and arrives at the router as '../../etc/passwd'.
    """
    r = await editor_client.get("/docs/%2e%2e/%2e%2e/etc/passwd")
    assert r.status_code == 400


async def test_path_traversal_create_blocked(editor_client):
    """POST with traversal path in JSON body must return 400."""
    r = await editor_client.post("/docs", json={
        "title": "Evil",
        "path": "../../tmp/evil.md",
        "body": "bad",
        "tags": [],
    })
    assert r.status_code == 400


async def test_path_traversal_update_blocked(editor_client):
    """PUT with traversal path must return 400.

    Uses percent-encoded dots (%2e) so the traversal survives HTTPX URL
    normalization and arrives at the router as '../../etc/shadow'.
    """
    r = await editor_client.put("/docs/%2e%2e/%2e%2e/etc/shadow", json={"title": "x"})
    assert r.status_code == 400


async def test_cors_allowed_origin(client):
    """Requests from allowed origin include CORS headers."""
    r = await client.options("/health", headers={
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


async def test_cors_disallowed_origin(client):
    """Requests from unknown origin do not get CORS allow header."""
    r = await client.options("/health", headers={
        "Origin": "http://evil.example.com",
        "Access-Control-Request-Method": "GET",
    })
    assert r.headers.get("access-control-allow-origin") != "http://evil.example.com"
