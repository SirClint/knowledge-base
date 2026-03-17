import pytest
import httpx
from unittest.mock import AsyncMock, patch


# ── Prompt construction — high value: verifies what the AI actually sees ──────

async def test_classify_ingestion_includes_folder_context_in_prompt():
    """Available folders and existing docs must both appear in the prompt,
    with docs listed before folders (AI needs context before instructions)."""
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
    """Titles must reach the AI prompt — paths alone are insufficient for topic matching.
    Regression for the pi bug: AI missed updates because it only saw slugified paths."""
    captured = {}

    async def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return AsyncMock(json=lambda: {"response": '{"action": "update", "path": "personal/pi.md", "title": "Pi", "body": "More pi info.", "needs_review": false, "reason": ""}'})

    with patch("ai.service.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = fake_post
        from ai.service import classify_ingestion_intent
        await classify_ingestion_intent(
            "Here is more information about pi",
            candidate_docs=[{"path": "personal/pi.md", "title": "Pi - Mathematical Constant"}],
        )
        prompt = captured["payload"]["prompt"]
        assert "Pi - Mathematical Constant" in prompt
        assert "personal/pi.md" in prompt


# ── merge_doc_content returns raw text, not JSON ──────────────────────────────

async def test_merge_doc_content_returns_raw_response():
    """merge_doc_content must return the raw AI response (not JSON-extracted).
    If it ever tried to parse JSON here the merge would silently fail."""
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


# ── Error handling — network failure must produce 503, not 500 ────────────────

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
