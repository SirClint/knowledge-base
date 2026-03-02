from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document
from ai.service import classify_ingestion_intent
from docs_.service import create_doc, update_doc


async def ingest_message(message: str, session: AsyncSession) -> dict:
    # Get existing doc paths for context
    result = await session.execute(select(Document.path))
    paths = [r[0] for r in result.fetchall()]

    intent = await classify_ingestion_intent(message, paths)
    action = intent.get("action", "create")
    path = intent.get("path", "")
    title = intent.get("title", "Untitled")
    body = intent.get("body", message)

    if action == "update" and path:
        await update_doc(path, {"title": title, "body": body}, session)
        return {"action": "update", "path": path, "message": f"Updated doc: {title}. Done."}
    else:
        if not path:
            slug = title.lower().replace(" ", "-")[:40]
            path = f"team/processes/{slug}.md"
        await create_doc(path, title, body, [], "", session)
        return {"action": "create", "path": path, "message": f"Created doc: {title}. Done."}
