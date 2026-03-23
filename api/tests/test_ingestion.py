import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient
from main import app
from tests.conftest import create_test_user


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


def _mock_session(existing_docs=None):
    """Build a mock DB session.

    existing_docs: list of (path, title) tuples returned by the Document query.
    Defaults to empty (no existing docs).
    """
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = existing_docs or []
    session.execute.return_value = result
    return session


# ── Regression: titles must reach the AI, not just slugged paths ──────────────

async def test_ingest_passes_titles_to_ai_for_topic_matching():
    """ingest_message must pass {path, title} dicts to classify_ingestion_intent.

    Passing only paths caused the AI to miss same-topic matches when the
    filename slug didn't clearly reflect the document title (e.g. the pi bug).
    """
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["candidate_docs"] = candidate_docs
        return {"action": "update", "path": "personal/pi.md", "title": "Pi", "body": "More info.", "reason": ""}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.search_semantic", new=AsyncMock(return_value=[])):
                with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    session = _mock_session(existing_docs=[("personal/pi.md", "Pi - Mathematical Constant")])
                    await ingest_message("Here is more information about pi", session=session)

    assert captured["candidate_docs"] == [{"path": "personal/pi.md", "title": "Pi - Mathematical Constant"}]


# ── Regression: update must merge with existing content, not replace it ───────

async def test_ingest_update_merges_with_existing_content():
    """When the AI returns action=update, the new message must be merged into the
    existing vault file body — not replace it.  Regression: previously update_doc was
    called with only the new message body, silently discarding the existing content.
    """
    mock_doc = MagicMock()

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update",
        "path": "personal/pi.md",
        "title": "Pi",
        "body": "Pi is transcendental.",   # AI-reformatted new message only
        "reason": "",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service._read_vault_body", return_value="Pi equals 3.14159..."):
                with patch("ingestion.service.merge_doc_content",
                           new=AsyncMock(return_value="Pi equals 3.14159...\n\nPi is transcendental.")) as mock_merge:
                    with patch("ingestion.service.update_doc", new=AsyncMock(return_value=mock_doc)) as mock_update:
                        from ingestion.service import ingest_message
                        result = await ingest_message(
                            "Pi is transcendental.",
                            session=_mock_session(existing_docs=[("personal/pi.md", "Pi")]),
                        )

    assert result["action"] == "update"
    mock_merge.assert_called_once_with("Pi equals 3.14159...", "Pi is transcendental.")
    call_updates = mock_update.call_args[0][1]
    assert call_updates["body"] == "Pi equals 3.14159...\n\nPi is transcendental."


async def test_ingest_same_topic_twice_updates_not_creates():
    """Two sequential ingests about the same topic: the second must update the first
    document, with its content merged in, rather than creating a second document.
    """
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create", "path": "personal/pi.md", "title": "Pi",
        "body": "Pi equals approximately 3.14159.", "reason": "",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                from ingestion.service import ingest_message
                r1 = await ingest_message("Pi equals approximately 3.14159.", session=_mock_session())
    assert r1["action"] == "create"

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update", "path": "personal/pi.md", "title": "Pi",
        "body": "Pi is a transcendental number.", "reason": "",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service._read_vault_body", return_value="Pi equals approximately 3.14159."):
                with patch("ingestion.service.merge_doc_content",
                           new=AsyncMock(return_value="Pi equals approximately 3.14159.\n\nPi is a transcendental number.")) as mock_merge:
                    with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())) as mock_update:
                        r2 = await ingest_message("Pi is a transcendental number.", session=_mock_session(
                            existing_docs=[("personal/pi.md", "Pi")]
                        ))

    assert r2["action"] == "update"
    assert r2["path"] == "personal/pi.md"
    mock_merge.assert_called_once()
    merged_body = mock_update.call_args[0][1]["body"]
    assert "3.14159" in merged_body
    assert "transcendental" in merged_body


# ── Regression: hallucinated update path must fall through to create ──────────

async def test_ingest_update_with_hallucinated_path_falls_back_to_create():
    """If the AI returns action=update but the path it chose is not in the existing
    docs list, it hallucinated a path.  The service must fall back to create so the
    content is not silently discarded.
    """
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update",
        "path": "team/processes/made-up-path.md",
        "title": "Some Doc",
        "body": "Content.",
        "reason": "",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())) as mock_create:
                from ingestion.service import ingest_message
                result = await ingest_message("Content.", session=_mock_session(
                    existing_docs=[("personal/other.md", "Other Doc")]
                ))

    assert result["action"] == "create"
    mock_create.assert_called_once()


async def test_ingest_does_not_set_needs_review_when_confident():
    mock_doc = MagicMock()
    mock_doc.status = "current"

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "team/processes/deploy.md",
        "title": "Deploy Process",
        "body": "Steps.",
        "needs_review": False,
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
                from ingestion.service import ingest_message
                result = await ingest_message("Deploy process steps...", session=_mock_session())
                assert result["needs_review"] is False
                assert mock_doc.status == "current"


async def test_ingest_passes_vault_subfolders_to_ai():
    """ingest_message must scan vault subfolders and pass them to classify_ingestion_intent."""
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["known_subfolders"] = known_subfolders
        return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "Body."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=["team/processes", "team/history"]):
            with patch("ingestion.service.search_semantic", new=AsyncMock(return_value=[])):
                with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    await ingest_message("test message", session=_mock_session())

    assert captured["known_subfolders"] == ["team/processes", "team/history"]


async def test_ingest_passes_semantic_candidates_to_ai():
    """ingest_message must call search_semantic and pass enriched results to
    classify_ingestion_intent as semantic_candidates."""
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["semantic_candidates"] = semantic_candidates
        return {"action": "update", "path": "team/sports/2026-winter-paralympics.md",
                "title": "2026 Winter Paralympics", "body": "Updated."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.search_semantic", new=AsyncMock(return_value=[
                {"path": "team/sports/2026-winter-paralympics.md", "score": 0.91},
            ])):
                with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    session = _mock_session(existing_docs=[
                        ("team/sports/2026-winter-paralympics.md", "2026 Winter Paralympics")
                    ])
                    await ingest_message("More info about the Winter Paralympics", session=session)

    assert captured["semantic_candidates"] is not None
    assert len(captured["semantic_candidates"]) == 1
    assert captured["semantic_candidates"][0]["path"] == "team/sports/2026-winter-paralympics.md"
    assert captured["semantic_candidates"][0]["title"] == "2026 Winter Paralympics"
    assert captured["semantic_candidates"][0]["score"] == pytest.approx(0.91)


async def test_ingest_falls_back_gracefully_when_search_semantic_fails():
    """If search_semantic raises (e.g. embedding model offline), ingest_message
    must still call classify_ingestion_intent — with semantic_candidates=None."""
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, semantic_candidates=None):
        captured["semantic_candidates"] = semantic_candidates
        return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "Body."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.search_semantic",
                       new=AsyncMock(side_effect=Exception("embedding model offline"))):
                with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    await ingest_message("test message", session=_mock_session())

    # Must have been called — fallback means semantic_candidates is None, not an exception
    assert "semantic_candidates" in captured
    assert captured["semantic_candidates"] is None


async def test_ingest_returns_reason_from_ai():
    """ingest_message must include the AI reason in its return value."""
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "team/history/zenobia.md",
        "title": "Zenobia",
        "body": "Historical queen of Palmyra.",
        "reason": "Created new subfolder team/history for historical content.",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                from ingestion.service import ingest_message
                result = await ingest_message("Zenobia was queen of Palmyra.", session=_mock_session())

    assert result["reason"] == "Created new subfolder team/history for historical content."


# ── Regression: heading-only body must not produce an empty document ──────────

async def test_ingest_body_fallback_when_heading_strip_empties_body():
    """If the AI returns a body consisting only of the title heading, stripping it
    must not produce an empty body — fall back to the raw message.
    Reproduces: The Corleck Head document created with no body content.
    """
    raw_message = "The Corleck Head is a 1st century CE Iron Age stone sculpture."
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, **kwargs):
        return {
            "action": "create",
            "path": "team/history/corleck-head.md",
            "title": "The Corleck Head",
            "body": "# The Corleck Head",   # only a heading — nothing else
            "reason": "New document.",
        }

    async def fake_create(path, title, body, tags, owner, session):
        captured["body"] = body
        return MagicMock()

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=fake_create):
                from ingestion.service import ingest_message
                await ingest_message(raw_message, session=_mock_session())

    assert captured["body"], "body must not be empty after heading strip"
    assert captured["body"] == raw_message


async def test_ingest_body_fallback_when_ai_returns_empty_body():
    """If the AI returns an empty body, ingest_message must fall back to the raw message."""
    raw_message = "Important content that must not be lost."
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None, **kwargs):
        return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "", "reason": "Created."}

    async def fake_create(path, title, body, tags, owner, session):
        captured["body"] = body
        return MagicMock()

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=fake_create):
                from ingestion.service import ingest_message
                await ingest_message(raw_message, session=_mock_session())

    assert captured["body"] == raw_message


# ── needs_review status is applied correctly ──────────────────────────────────

async def test_ingest_sets_needs_review_status_on_doc():
    mock_doc = MagicMock()
    mock_doc.status = "current"

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create", "path": "personal/vague-note.md",
        "title": "Vague Note", "body": "Some content.", "needs_review": True, "reason": "",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
                from ingestion.service import ingest_message
                result = await ingest_message("something vague", session=_mock_session())
                assert result["needs_review"] is True
                assert mock_doc.status == "needs_review"


# ── Role-based access control for POST /ingest ────────────────────────────────

async def test_reader_cannot_ingest(client):
    """Readers must receive 403 on POST /ingest."""
    import auth.users  # noqa
    from db.database import create_db
    await create_db()
    await create_test_user("reader@test.com", "Securepass1!", "reader")
    r = await client.post("/auth/jwt/login", data={"username": "reader@test.com", "password": "Securepass1!"})
    token = r.json()["access_token"]
    r = await client.post("/ingest", json={"message": "test"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


