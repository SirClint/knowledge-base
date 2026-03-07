from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db.database import get_session
from ingestion.service import ingest_message
from auth.users import current_active_user

router = APIRouter(prefix="/ingest", tags=["ingestion"])


class IngestPayload(BaseModel):
    message: str
    reply_to: str = ""  # email/chat address to reply to (platform TBD)


@router.post("")
async def ingest(payload: IngestPayload, session=Depends(get_session), user=Depends(current_active_user)):
    try:
        result = await ingest_message(payload.message, session)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
