import pytest
import httpx
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
        result = await classify_ingestion_intent("something vague", candidate_docs=[])
        assert result["needs_review"] is True
        assert "action" in result
        assert "path" in result


async def test_classify_ingestion_includes_folder_context_in_prompt():
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "create", "path": "team/history/design.md", "title": "Design", "body": "Body.", "needs_review": false, "reason": "Created team/history for historical content."}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent(
            "architecture doc",
            candidate_docs=[{"path": "personal/existing.md", "title": "Existing Doc"}],
            known_subfolders=["team/processes", "team/systems"],
        )
        prompt = captured["payload"]["prompt"]
        assert "Existing documents" in prompt
        assert "Known folders" in prompt
        assert "team/processes" in prompt
        assert "team/systems" in prompt
        assert prompt.index("Existing documents") < prompt.index("Known folders")


async def test_classify_ingestion_returns_reason():
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": '{"action": "create", "path": "team/history/zenobia.md", "title": "Zenobia", "body": "Historical queen.", "needs_review": false, "reason": "Created new subfolder team/history for historical content."}'}
        ))
        from ai.service import classify_ingestion_intent
        result = await classify_ingestion_intent("Zenobia was a queen.", candidate_docs=[])
        assert result["reason"] == "Created new subfolder team/history for historical content."


async def test_classify_ingestion_prompt_includes_doc_titles():
    """Titles must reach the AI prompt — paths alone are insufficient for topic matching."""
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "update", "path": "personal/pi.md", "title": "Pi", "body": "More pi info.", "needs_review": false}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent(
            "Here is more information about pi",
            candidate_docs=[{"path": "personal/pi.md", "title": "Pi - Mathematical Constant"}],
        )
        prompt = captured["payload"]["prompt"]
        # The human-readable title must appear in the prompt so the AI can
        # match by topic rather than guessing from a slugified filename.
        assert "Pi - Mathematical Constant" in prompt
        assert "personal/pi.md" in prompt


async def test_merge_doc_content():
    """merge_doc_content should return the raw AI response (not JSON-extracted)."""
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(return_value=AsyncMock(
            json=lambda: {"response": "# Pi\n\nPi equals 3.14159.\n\nPi is also transcendental."}
        ))
        from ai.service import merge_doc_content
        result = await merge_doc_content(
            existing_body="Pi equals 3.14159.",
            new_message="Pi is also a transcendental number.",
        )
        assert "3.14159" in result
        assert "transcendental" in result


async def test_classify_ingestion_prompt_includes_semantic_candidates():
    """When semantic_candidates are provided they must appear in the prompt
    so the model treats them as strong update candidates."""
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "update", "path": "team/sports/2026-winter-paralympics.md", "title": "Paralympics", "body": "Updated.", "needs_review": false, "reason": "Updated team/sports because semantic match found."}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent(
            "More info about the Winter Paralympics",
            candidate_docs=[{"path": "team/sports/2026-winter-paralympics.md", "title": "2026 Winter Paralympics"}],
            semantic_candidates=[{"path": "team/sports/2026-winter-paralympics.md", "title": "2026 Winter Paralympics", "score": 0.91}],
        )
        prompt = captured["payload"]["prompt"]
        assert "2026 Winter Paralympics" in prompt
        assert "0.91" in prompt
        assert "Semantic" in prompt or "semantic" in prompt


async def test_ollama_connect_error_raises_runtime_error():
    """Network errors from Ollama must become RuntimeError, not propagate as raw httpx
    exceptions.  The ingestion router catches RuntimeError and returns 503 so the
    user sees a clear 'AI unavailable' message instead of a generic 500."""
    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("All connection attempts failed")
        )
        from ai.service import classify_ingestion_intent
        with pytest.raises(RuntimeError, match="AI service is unreachable"):
            await classify_ingestion_intent("test", candidate_docs=[])
