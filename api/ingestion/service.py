from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from db.models import Document
from ai.service import classify_ingestion_intent
from docs_.service import create_doc, update_doc


def _normalize_path(path: str) -> str:
    """Normalize an AI-generated doc path.

    - Strip leading slash (AI sometimes returns /personal/foo.md)
    - Ensure .md extension
    """
    path = path.lstrip("/").strip()
    if path and not path.endswith(".md"):
        path += ".md"
    return path


async def ingest_message(message: str, session: AsyncSession) -> dict:
    # Get existing doc paths for context
    result = await session.execute(select(Document.path))
    paths = [r[0] for r in result.fetchall()]

    intent = await classify_ingestion_intent(message, paths)
    action = intent.get("action", "create")
    path = _normalize_path(intent.get("path", ""))
    title = intent.get("title", "Untitled")
    body = intent.get("body") or message
    needs_review = intent.get("needs_review", False)

    if action == "update" and path:
        doc = await update_doc(path, {"title": title, "body": body}, session, saved_by="ingestion")
        if needs_review and doc:
            doc.status = "needs_review"
            await session.commit()
        return {"action": "update", "path": path, "needs_review": needs_review, "message": f"Updated doc: {title}."}
    else:
        if not path:
            slug = title.lower().replace(" ", "-")[:40]
            path = f"personal/{slug}.md"
        try:
            doc = await create_doc(path, title, body, [], "", session)
        except IntegrityError:
            # Path already exists — update instead
            await session.rollback()
            doc = await update_doc(path, {"title": title, "body": body}, session, saved_by="ingestion")
            action = "update"
        if needs_review and doc:
            doc.status = "needs_review"
            await session.commit()
        return {"action": action, "path": path, "needs_review": needs_review, "message": f"{'Updated' if action == 'update' else 'Created'} doc: {title}."}
