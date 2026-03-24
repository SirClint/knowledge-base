import pytest
import hmac
import hashlib
import time
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app


def make_mailgun_signature(signing_key: str, timestamp: str, token: str) -> str:
    return hmac.new(
        key=signing_key.encode(),
        msg=f"{timestamp}{token}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


@pytest.fixture
async def client():
    import auth.users  # noqa: F401
    from db.database import create_db
    await create_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_email_ingestion_valid(client):
    signing_key = "test-signing-key"
    timestamp = str(int(time.time()))
    token = "test-token-abc123"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    mock_result = {"action": "create", "path": "personal/test.md", "needs_review": False, "message": "Created doc: Test."}

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"), \
         patch("ingestion.router.ingest_message", new=AsyncMock(return_value=mock_result)):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            "sender": "sender@example.com",
            "subject": "Meeting Notes",
            "body-plain": "These are the notes from today's meeting.",
        })
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_email_ingestion_invalid_signature(client):
    timestamp = str(int(time.time()))
    with patch("config.settings.mailgun_webhook_signing_key", "real-key"), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": "sometoken",
            "signature": "wrongsignature",
            "sender": "sender@example.com",
            "subject": "Test",
            "body-plain": "body",
        })
    assert r.status_code == 403


async def test_email_ingestion_sender_not_whitelisted(client):
    signing_key = "test-key"
    timestamp = str(int(time.time()))
    token = "tok"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "allowed@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            "sender": "notallowed@example.com",
            "subject": "Test",
            "body-plain": "body",
        })
    assert r.status_code == 403


async def test_email_ingestion_no_signing_key_configured(client):
    """When no signing key is configured, reject all requests."""
    with patch("config.settings.mailgun_webhook_signing_key", ""), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": "12345",
            "token": "tok",
            "signature": "sig",
            "sender": "sender@example.com",
            "subject": "Test",
            "body-plain": "body",
        })
    assert r.status_code == 403


async def test_email_token_dedup_rejected(client):
    """Second request with same Mailgun token must be rejected with 403."""
    signing_key = "test-signing-key"
    timestamp = str(int(time.time()))
    token = "unique-token-dedup-test"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    data = {
        "timestamp": timestamp,
        "token": token,
        "signature": signature,
        "sender": "sender@example.com",
        "subject": "Test",
        "body-plain": "content",
    }

    mock_result = {"action": "create", "path": "personal/test.md", "needs_review": False, "message": "ok"}

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"), \
         patch("ingestion.router.ingest_message", new=AsyncMock(return_value=mock_result)):
        r1 = await client.post("/ingest/email", data=data)
        assert r1.status_code == 200

        r2 = await client.post("/ingest/email", data=data)
        assert r2.status_code == 403


async def test_email_body_size_cap(client):
    """Email body exceeding 50,000 chars is rejected with 413."""
    signing_key = "test-signing-key"
    timestamp = str(int(time.time()))
    token = "size-cap-token-abc"
    signature = make_mailgun_signature(signing_key, timestamp, token)

    with patch("config.settings.mailgun_webhook_signing_key", signing_key), \
         patch("config.settings.ingest_email_whitelist", "sender@example.com"):
        r = await client.post("/ingest/email", data={
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
            "sender": "sender@example.com",
            "subject": "Big",
            "body-plain": "x" * 50_001,
        })
    assert r.status_code == 413
