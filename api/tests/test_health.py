import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_ai_online(client):
    mock_inner_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_inner_client.get = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        r = await client.get("/health/ai")
    assert r.status_code == 200
    assert r.json() == {"ai": "online"}


async def test_health_ai_offline(client):
    import httpx
    mock_inner_client = AsyncMock()
    mock_inner_client.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        r = await client.get("/health/ai")
    assert r.status_code == 200
    assert r.json() == {"ai": "offline"}
