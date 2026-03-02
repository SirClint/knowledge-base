import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document
from docs_.parser import parse_doc


async def index_file(path: Path, session: AsyncSession) -> Document:
    parsed = parse_doc(path)
    result = await session.execute(
        select(Document).where(Document.path == str(path))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        doc = Document(path=str(path))
        session.add(doc)
    doc.title = parsed.title
    doc.tags = json.dumps(parsed.tags)
    doc.owner = parsed.owner
    doc.status = parsed.status
    doc.created = parsed.created
    doc.last_reviewed = parsed.last_reviewed
    doc.review_interval = parsed.review_interval
    doc.body_preview = parsed.body[:500]
    await session.commit()
    from search.service import index_doc_vectors
    await index_doc_vectors(str(doc.id), str(path), parsed.body)
    return doc


async def index_vault(vault_path: Path, session: AsyncSession):
    for md_file in vault_path.rglob("*.md"):
        await index_file(md_file, session)
