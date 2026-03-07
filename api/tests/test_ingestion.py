import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_session():
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = []
    session.execute.return_value = result
    return session


async def test_ingest_creates_new_doc():
    with patch("ingestion.service.classify_ingestion_intent", new=AsyncMock(return_value={
        "action": "create",
        "path": "team/processes/new-process.md",
        "title": "New Process",
        "body": "Steps for the new process.",
    })):
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
        with patch("ingestion.service.update_doc", new=AsyncMock(return_value=MagicMock())):
            from ingestion.service import ingest_message
            result = await ingest_message("Update the deploy doc: now use Docker 24", session=_mock_session())
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
        with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
            from ingestion.service import ingest_message
            result = await ingest_message("something vague", session=_mock_session())
            assert result["needs_review"] is True
            assert mock_doc.status == "needs_review"


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
        with patch("ingestion.service.create_doc", new=AsyncMock(return_value=mock_doc)):
            from ingestion.service import ingest_message
            result = await ingest_message("Deploy process steps...", session=_mock_session())
            assert result["needs_review"] is False
            assert mock_doc.status == "current"
