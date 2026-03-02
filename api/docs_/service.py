import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Document
from config import settings
import frontmatter


async def write_doc_file(path: str, title: str, body: str, meta: dict):
    full_path = Path(settings.vault_path) / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **{"title": title, **meta})
    full_path.write_text(frontmatter.dumps(post))


async def create_doc(path: str, title: str, body: str, tags: list, owner: str, session: AsyncSession) -> Document:
    meta = {"tags": tags, "owner": owner, "status": "current"}
    await write_doc_file(path, title, body, meta)
    doc = Document(path=path, title=title, tags=json.dumps(tags), owner=owner, body_preview=body[:500])
    session.add(doc)
    await session.commit()
    # Index into vector store for semantic search
    from search.service import index_doc_vectors
    try:
        await index_doc_vectors(str(doc.id), path, f"{title}\n{body}")
    except Exception:
        pass  # Don't fail doc creation if Ollama is unavailable
    return doc


async def get_doc(path: str, session: AsyncSession) -> Document | None:
    result = await session.execute(select(Document).where(Document.path == path))
    return result.scalar_one_or_none()


async def update_doc(path: str, updates: dict, session: AsyncSession) -> Document | None:
    doc = await get_doc(path, session)
    if not doc:
        return None
    for key, value in updates.items():
        setattr(doc, key, value)
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        if "title" in updates:
            post.metadata["title"] = updates["title"]
        if "body" in updates:
            post.content = updates["body"]
        full_path.write_text(frontmatter.dumps(post))
    await session.commit()
    return doc


async def delete_doc(path: str, session: AsyncSession) -> bool:
    doc = await get_doc(path, session)
    if not doc:
        return False
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        full_path.unlink()
    await session.delete(doc)
    await session.commit()
    return True
