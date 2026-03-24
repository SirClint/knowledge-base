import pytest
from unittest.mock import patch, AsyncMock, MagicMock
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


async def test_health_ai_online(editor_client):
    mock_inner_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_inner_client.get = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        r = await editor_client.get("/health/ai")
    assert r.status_code == 200
    assert r.json() == {"ai": "online"}


async def test_health_ai_offline(editor_client):
    import httpx
    mock_inner_client = AsyncMock()
    mock_inner_client.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        r = await editor_client.get("/health/ai")
    assert r.status_code == 200
    assert r.json() == {"ai": "offline"}
