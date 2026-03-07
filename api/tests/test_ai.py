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


async def test_classify_ingestion_returns_needs_review():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '{"action": "create", "path": "personal/vague-note.md", "title": "Vague Note", "body": "Some content.", "needs_review": true}'}
        ))
        from ai.service import classify_ingestion_intent
        result = await classify_ingestion_intent("something vague", candidate_paths=[])
        assert result["needs_review"] is True
        assert "action" in result
        assert "path" in result


async def test_classify_ingestion_includes_known_folders_in_prompt():
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "create", "path": "team/architecture/design.md", "title": "Design", "body": "Body.", "needs_review": false}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent("architecture doc", candidate_paths=["personal/existing.md"])
        prompt = captured["payload"]["prompt"]
        assert "Existing doc paths:" in prompt
        assert "Available folders:" in prompt
        assert prompt.index("Existing doc paths:") < prompt.index("Available folders:")
        assert "team/architecture" in prompt
