"""Real-model integration tests for AI ingestion.

These tests call the actual Ollama endpoint and exercise the full ingestion
pipeline — no mocks on the AI layer.  They catch:
  - Model output format changes (invalid JSON, missing fields)
  - Empty or heading-only bodies (the Corleck Head bug)
  - Paths containing literal 'subfolder' or other bad patterns
  - create vs. update decision with a real knowledge base context

Tests skip automatically when Ollama is unreachable.

Run directly:
  docker compose -f docker-compose.test.yml --env-file .env.test \
    exec api pytest tests/test_ingestion_integration.py -v
"""
import re
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── Skip guard ────────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    try:
        r = httpx.get("http://host.docker.internal:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama not reachable — skipping real-model integration tests",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_session(existing_docs=None):
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = existing_docs or []
    session.execute.return_value = result
    return session


# ── classify_ingestion_intent — real model output shape ───────────────────────

async def test_real_classify_returns_all_required_fields():
    """Real model must return all fields the service depends on."""
    from ai.service import classify_ingestion_intent
    result = await classify_ingestion_intent(
        "The Battle of Hastings was fought in 1066 between Harold II and William the Conqueror.",
        candidate_docs=[],
    )
    assert "action" in result, "missing 'action'"
    assert "path" in result, "missing 'path'"
    assert "title" in result, "missing 'title'"
    assert "body" in result, "missing 'body'"
    assert "needs_review" in result, "missing 'needs_review'"
    assert "reason" in result, "missing 'reason'"


async def test_real_classify_action_is_valid():
    from ai.service import classify_ingestion_intent
    result = await classify_ingestion_intent(
        "Zenobia was the 3rd-century queen of the Palmyrene Empire.",
        candidate_docs=[],
    )
    assert result["action"] in ("create", "update"), f"unexpected action: {result['action']}"


async def test_real_classify_body_is_not_empty():
    """The body must never be empty — this is the root cause of the Corleck Head bug."""
    from ai.service import classify_ingestion_intent
    result = await classify_ingestion_intent(
        "The Corleck Head is a 1st-century Iron Age stone carving found in County Cavan, Ireland. "
        "It depicts three faces on a single stone.",
        candidate_docs=[],
    )
    assert result.get("body", "").strip(), (
        f"body is empty — model returned: {result}"
    )


async def test_real_classify_path_format_is_valid():
    """Path must follow root/topic/slug.md — no literal 'subfolder', no spaces, no uppercase."""
    from ai.service import classify_ingestion_intent
    result = await classify_ingestion_intent(
        "Our team retro notes from last Friday: we should improve PR review turnaround.",
        candidate_docs=[],
    )
    path = result.get("path", "")
    assert path.endswith(".md"), f"path must end in .md: {path!r}"
    assert " " not in path, f"path must not contain spaces: {path!r}"
    assert path == path.lower(), f"path must be lowercase: {path!r}"
    assert "subfolder" not in path.lower(), f"path must not contain literal 'subfolder': {path!r}"
    parts = path.split("/")
    assert len(parts) >= 2, f"path must be at least root/file.md: {path!r}"


async def test_real_classify_path_uses_known_root_folder():
    """Path must start with a known root folder (personal or team)."""
    from ai.service import classify_ingestion_intent
    result = await classify_ingestion_intent(
        "My favourite recipe is pasta carbonara: eggs, guanciale, pecorino, and black pepper.",
        candidate_docs=[],
        known_subfolders=["personal/cooking", "personal/notes", "team/processes"],
    )
    path = result.get("path", "")
    root = path.split("/")[0]
    assert root in ("personal", "team"), f"path must start with 'personal' or 'team', got: {path!r}"


async def test_real_classify_body_contains_meaningful_content():
    """Body must contain words from the original message — not just a heading."""
    message = "The Rosetta Stone is a granodiorite stele inscribed with a decree from 196 BC."
    from ai.service import classify_ingestion_intent
    result = await classify_ingestion_intent(message, candidate_docs=[])
    body = result.get("body", "")
    # At least one distinctive word from the message should appear in the body
    assert any(word in body for word in ["Rosetta", "granodiorite", "196", "decree", "stele"]), (
        f"body doesn't contain content from the original message.\n"
        f"Original: {message}\nBody: {body!r}"
    )


# ── Full ingest_message pipeline — real model + real document creation ────────

async def test_real_ingest_produces_non_empty_body():
    """End-to-end: ingest_message must call create_doc with a non-empty body.
    This is the definitive regression test for the Corleck Head bug."""
    captured = {}

    async def fake_create(path, title, body, tags, owner, session):
        captured["body"] = body
        captured["path"] = path
        return MagicMock()

    with patch("ingestion.service.create_doc", new=fake_create):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            from ingestion.service import ingest_message
            await ingest_message(
                "The Giant's Causeway in Northern Ireland consists of around 40,000 interlocking "
                "basalt columns formed by an ancient volcanic eruption.",
                session=_mock_session(),
            )

    assert captured.get("body", "").strip(), (
        f"create_doc was called with an empty body. Path: {captured.get('path')}"
    )


async def test_real_ingest_path_does_not_contain_subfolder():
    """Full pipeline: the normalized path must never contain the literal word 'subfolder'."""
    captured = {}

    async def fake_create(path, title, body, tags, owner, session):
        captured["path"] = path
        return MagicMock()

    with patch("ingestion.service.create_doc", new=fake_create):
        with patch("ingestion.service._scan_vault_subfolders", return_value=["team/history", "personal/notes"]):
            from ingestion.service import ingest_message
            await ingest_message(
                "Quick note: remember to book flights for the team offsite in June.",
                session=_mock_session(),
            )

    path = captured.get("path", "")
    assert "subfolder" not in path.lower(), f"path contains literal 'subfolder': {path!r}"


async def test_real_ingest_update_preserves_existing_content():
    """When AI returns update, existing vault content must be merged in, not overwritten."""
    existing_body = "The Titanic sank on April 15, 1912 after hitting an iceberg."
    merged_bodies = []

    async def fake_update(path, updates, session, saved_by=""):
        merged_bodies.append(updates.get("body", ""))
        return MagicMock()

    with patch("ingestion.service.update_doc", new=fake_update):
        with patch("ingestion.service._read_vault_body", return_value=existing_body):
            with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
                from ingestion.service import ingest_message
                await ingest_message(
                    "Over 1,500 people died when the Titanic sank, making it one of the deadliest peacetime maritime disasters.",
                    session=_mock_session(existing_docs=[("team/history/titanic.md", "RMS Titanic")]),
                )

    if merged_bodies:
        # If the AI chose update, the merged body must retain the original content
        assert "1912" in merged_bodies[0] or "iceberg" in merged_bodies[0], (
            f"Existing content was lost in merge. Merged body: {merged_bodies[0]!r}"
        )
