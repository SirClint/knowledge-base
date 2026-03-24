import hmac
import hashlib
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import jwt
from db.database import get_session
from ingestion.service import ingest_message
from auth.users import current_active_user, require_editor
from config import settings
from slowapi.util import get_remote_address
from limiter import limiter  # MUST import from limiter.py, NOT from main (avoids circular import)


def _key_by_user(request: Request) -> str:
    """Rate-limit /ingest per authenticated user, falling back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ")
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            return payload.get("sub") or get_remote_address(request)
        except jwt.PyJWTError:
            pass
    return get_remote_address(request)


router = APIRouter(prefix="/ingest", tags=["ingestion"])

# NOTE: The @limiter.limit decorator below is always active regardless of settings.rate_limit_enabled.
# The PathRateLimitMiddleware in main.py checks rate_limit_enabled, but slowapi decorators
# on individual routes do not. This means /ingest per-user limit is always enforced.


class IngestPayload(BaseModel):
    message: str
    reply_to: str = ""


def _verify_mailgun_signature(signing_key: str, timestamp: str, token: str, signature: str) -> bool:
    """Verify Mailgun webhook HMAC-SHA256 signature."""
    if not signing_key:
        return False
    try:
        # Reject timestamps older than 15 minutes
        if abs(int(timestamp) - int(time.time())) > 900:
            return False
    except (ValueError, TypeError):
        return False
    computed = hmac.new(
        key=signing_key.encode(),
        msg=f"{timestamp}{token}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("")
@limiter.limit("30/minute", key_func=_key_by_user)
async def ingest(request: Request, payload: IngestPayload, session=Depends(get_session), user=Depends(require_editor)):
    try:
        result = await ingest_message(payload.message, session, owner=user.email)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"AI processing failed: {e}")


@router.post("/email")
async def ingest_email(request: Request, session=Depends(get_session)):
    form = await request.form()
    timestamp = form.get("timestamp", "")
    token = form.get("token", "")
    signature = form.get("signature", "")
    sender = form.get("sender", "")
    subject = form.get("subject", "")
    body_plain = form.get("body-plain", "")

    # Verify Mailgun signature
    if not _verify_mailgun_signature(settings.mailgun_webhook_signing_key, timestamp, token, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Check sender whitelist
    whitelist = [e.strip().lower() for e in settings.ingest_email_whitelist.split(",") if e.strip()]
    if not whitelist or sender.lower() not in whitelist:
        raise HTTPException(status_code=403, detail="Sender not authorized")

    # Combine subject + body and pass through existing AI ingestion pipeline
    message = f"{subject}\n\n{body_plain}".strip() if subject else body_plain
    try:
        await ingest_message(message, session)
    except ValueError as e:
        # Log but return 200 so Mailgun doesn't retry on AI errors
        print(f"Email ingestion AI error: {e}")
    return {"status": "queued"}
