import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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


async def test_ingest_creates_new_doc():
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "team/processes/new-process.md",
        "title": "New Process",
        "body": "Steps for the new process.",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=None)):
                from ingestion.service import ingest_message
                result = await ingest_message("We have a new onboarding process: ...", session=_mock_session())
                assert result["action"] == "create"
                assert "new-process" in result["path"]


async def test_ingest_updates_existing_doc():
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update",
        "path": "team/processes/deploy.md",
        "title": "Deploy Process",
        "body": "Updated deploy steps.",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service._read_vault_body", return_value=None):
                with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
                    from ingestion.service import ingest_message
                    result = await ingest_message(
                        "Update the deploy doc: now use Docker 24",
                        session=_mock_session(existing_docs=[("team/processes/deploy.md", "Deploy Process")]),
                    )
                    assert result["action"] == "update"


async def test_ingest_sets_needs_review_status_on_create():
    mock_doc = MagicMock()
    mock_doc.status = "current"

    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "personal/vague-note.md",
        "title": "Vague Note",
        "body": "Some content.",
        "needs_review": True,
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
                from ingestion.service import ingest_message
                result = await ingest_message("something vague", session=_mock_session())
                assert result["needs_review"] is True
                assert mock_doc.status == "needs_review"


async def test_ingest_passes_titles_to_ai_for_topic_matching():
    """ingest_message must pass {path, title} dicts to classify_ingestion_intent.

    Passing only paths caused the AI to miss same-topic matches when the
    filename slug didn't clearly reflect the document title (e.g. the pi bug).
    """
    captured = {}

    async def fake_classify(message, candidate_docs, known_subfolders=None):
        captured["candidate_docs"] = candidate_docs
        return {"action": "update", "path": "personal/pi.md", "title": "Pi", "body": "More info."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
                from ingestion.service import ingest_message
                session = _mock_session(existing_docs=[("personal/pi.md", "Pi - Mathematical Constant")])
                await ingest_message("Here is more information about pi", session=session)

    assert captured["candidate_docs"] == [{"path": "personal/pi.md", "title": "Pi - Mathematical Constant"}]


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
    # merge_doc_content must have been called with existing body + new message
    mock_merge.assert_called_once_with("Pi equals 3.14159...", "Pi is transcendental.")
    # update_doc must have received the merged body, not just the new message
    call_updates = mock_update.call_args[0][1]
    assert call_updates["body"] == "Pi equals 3.14159...\n\nPi is transcendental."


async def test_ingest_same_topic_twice_updates_not_creates():
    """Two sequential ingests about the same topic: the second must update the first
    document, with its content merged in, rather than creating a second document.
    This is the core pi scenario: ingest pi facts, then ingest more pi facts.
    """
    # First ingest creates the doc
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "personal/pi.md",
        "title": "Pi",
        "body": "Pi equals approximately 3.14159.",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                from ingestion.service import ingest_message
                r1 = await ingest_message("Pi equals approximately 3.14159.", session=_mock_session())
    assert r1["action"] == "create"

    # Second ingest: AI correctly identifies same topic → update
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update",
        "path": "personal/pi.md",
        "title": "Pi",
        "body": "Pi is a transcendental number.",
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
    assert "3.14159" in merged_body          # existing content preserved
    assert "transcendental" in merged_body   # new content incorporated


async def test_ingest_update_with_hallucinated_path_falls_back_to_create():
    """If the AI returns action=update but the path it chose is not in the existing
    docs list, it hallucinated a path.  The service must fall back to create so the
    content is not silently discarded.
    """
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "update",
        "path": "team/processes/made-up-path.md",   # not in candidate_docs
        "title": "Some Doc",
        "body": "Content.",
    })):
        with patch("ingestion.service._scan_vault_subfolders", return_value=[]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())) as mock_create:
                from ingestion.service import ingest_message
                # candidate_docs does NOT include made-up-path.md
                result = await ingest_message("Content.", session=_mock_session(
                    existing_docs=[("personal/other.md", "Other Doc")]
                ))

    assert result["action"] == "create"
    assert result["path"] == "team/processes/made-up-path.md"
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

    async def fake_classify(message, candidate_docs, known_subfolders=None):
        captured["known_subfolders"] = known_subfolders
        return {"action": "create", "path": "personal/test.md", "title": "Test", "body": "Body."}

    with patch("ingestion.service.classify_ingestion_intent", new=fake_classify):
        with patch("ingestion.service._scan_vault_subfolders", return_value=["team/processes", "team/history"]):
            with patch("ingestion.service.create_doc", new=AsyncMock(return_value=MagicMock())):
                from ingestion.service import ingest_message
                await ingest_message("test message", session=_mock_session())

    assert captured["known_subfolders"] == ["team/processes", "team/history"]


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
