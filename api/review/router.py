from fastapi import APIRouter, Depends
from db.database import get_session
from scheduler.jobs import get_overdue_docs
from auth.users import current_active_user

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue")
async def queue(session=Depends(get_session), user=Depends(current_active_user)):
    docs = await get_overdue_docs(session)
    return [
        {
            "id": d.id,
            "path": d.path,
            "title": d.title,
            "last_reviewed": d.last_reviewed,
            "reason": "AI-created, needs review" if d.status == "needs_review" else "Overdue for review",
        }
        for d in docs
    ]


@router.post("/{doc_id}/mark-reviewed", dependencies=[Depends(current_active_user)])
async def mark_reviewed(doc_id: int, session=Depends(get_session)):
    from sqlalchemy import select
    from db.models import Document
    from datetime import date
    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc:
        doc.last_reviewed = str(date.today())
        doc.status = "current"
        await session.commit()
    return {"marked_reviewed": True}
