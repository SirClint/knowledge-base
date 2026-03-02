from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document


def _parse_interval(interval: str) -> int:
    """Convert '30d' to 30, '90d' to 90."""
    return int(interval.rstrip("d"))


async def get_overdue_docs(session: AsyncSession) -> list[Document]:
    result = await session.execute(select(Document).where(Document.last_reviewed.isnot(None)))
    docs = result.scalars().all()
    overdue = []
    for doc in docs:
        try:
            reviewed = date.fromisoformat(doc.last_reviewed)
            interval = _parse_interval(doc.review_interval or "90d")
            if (date.today() - reviewed).days >= interval:
                overdue.append(doc)
        except (ValueError, TypeError):
            pass
    return overdue


async def run_staleness_check():
    """Called nightly by APScheduler."""
    from db.database import async_session_maker
    from ai.service import check_staleness
    from pathlib import Path
    from config import settings
    async with async_session_maker() as session:
        docs = await get_overdue_docs(session)
        for doc in docs:
            path = Path(settings.vault_path) / doc.path
            if not path.exists():
                continue
            body = path.read_text()
            result = await check_staleness(body)
            if result.get("stale"):
                doc.status = "needs_review"
                await session.commit()
