import json
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
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
    doc.created_at = datetime.utcnow()
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


async def update_doc(path: str, updates: dict, session: AsyncSession, saved_by: str = "") -> Document | None:
    doc = await get_doc(path, session)
    if not doc:
        return None

    # Snapshot current body before overwriting
    full_path = Path(settings.vault_path) / path
    if full_path.exists() and ("body" in updates or "title" in updates):
        from db.models import DocVersion

        post = frontmatter.load(str(full_path))
        current_body = post.content

        snapshot = DocVersion(doc_path=path, body=current_body, saved_by=saved_by)
        session.add(snapshot)
        await session.flush()

        # Prune: keep only the 50 most recent versions
        subq = (
            select(DocVersion.id)
            .where(DocVersion.doc_path == path)
            .order_by(DocVersion.saved_at.desc())
            .limit(50)
        ).subquery()
        await session.execute(
            delete(DocVersion).where(
                DocVersion.doc_path == path,
                DocVersion.id.not_in(select(subq.c.id))
            )
        )

    # Apply updates to DB record
    for key, value in updates.items():
        setattr(doc, key, value)

    # Apply updates to vault file
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        if "title" in updates:
            post.metadata["title"] = updates["title"]
        if "body" in updates:
            post.content = updates["body"]
        full_path.write_text(frontmatter.dumps(post))

    doc.updated_by = saved_by
    await session.commit()
    return doc


async def delete_doc(path: str, session: AsyncSession) -> bool:
    doc = await get_doc(path, session)
    if not doc:
        return False
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        full_path.unlink()
    # Clean up associated versions and comments
    from db.models import DocVersion, Comment
    await session.execute(delete(DocVersion).where(DocVersion.doc_path == path))
    await session.execute(delete(Comment).where(Comment.doc_path == path))
    await session.delete(doc)
    await session.commit()
    return True
