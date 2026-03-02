import pytest
from unittest.mock import AsyncMock, patch


async def test_suggest_tags():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '["kubernetes", "deployment", "infrastructure"]'}
        ))
        from ai.service import suggest_tags
        tags = await suggest_tags("Steps to deploy to Kubernetes production cluster", existing_tags=["kubernetes", "ci-cd"])
        assert isinstance(tags, list)
        assert all(t in ["kubernetes", "deployment", "infrastructure"] for t in tags)


async def test_check_staleness():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '{"stale": true, "reason": "References Docker version 19 which is outdated"}'}
        ))
        from ai.service import check_staleness
        result = await check_staleness("Use Docker 19 to build your image...")
        assert result["stale"] is True
        assert "reason" in result
