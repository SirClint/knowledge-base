from pathlib import Path
import frontmatter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from db.models import Document
from ai.service import classify_ingestion_intent, merge_doc_content, ROOT_FOLDERS
from docs_.service import create_doc, update_doc
from config import settings


def _normalize_path(path: str) -> str:
    """Normalize an AI-generated doc path.

    - Strip leading slash (AI sometimes returns /personal/foo.md)
    - Ensure .md extension
    """
    path = path.lstrip("/").strip()
    if path and not path.endswith(".md"):
        path += ".md"
    return path


def _read_vault_body(path: str) -> str | None:
    """Read the markdown body of an existing vault file.

    Returns None if the file does not exist, so callers can fall back to the
    AI-generated body rather than failing.
    """
    vault_file = Path(settings.vault_path) / path
    if not vault_file.exists():
        return None
    post = frontmatter.load(str(vault_file))
    return post.content


async def _update_with_merge(path: str, title: str, message: str, fallback_body: str,
                              session: AsyncSession) -> Document | None:
    """Update an existing doc, merging the new message into its current content.

    If the vault file is present, calls the AI to produce a merged document body.
    Falls back to fallback_body (AI-reformatted new message) if the file is missing.
    """
    existing_body = _read_vault_body(path)
    if existing_body is not None:
        merged = await merge_doc_content(existing_body, message)
    else:
        merged = fallback_body
    return await update_doc(path, {"title": title, "body": merged}, session, saved_by="ingestion")


def _scan_vault_subfolders() -> list[str]:
    """Scan vault for existing subfolders under each root folder."""
    vault = Path(settings.vault_path)
    subfolders = []
    for root in ROOT_FOLDERS:
        root_path = vault / root
        if root_path.is_dir():
            for child in sorted(root_path.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    subfolders.append(f"{root}/{child.name}")
    return subfolders


async def ingest_message(message: str, session: AsyncSession, owner: str = "") -> dict:
    # Get existing doc titles + paths for context so the AI can match by topic
    result = await session.execute(select(Document.path, Document.title))
    candidate_docs = [{"path": r[0], "title": r[1]} for r in result.fetchall()]

    known_subfolders = _scan_vault_subfolders()
    intent = await classify_ingestion_intent(message, candidate_docs, known_subfolders=known_subfolders)
    action = intent.get("action", "create")
    path = _normalize_path(intent.get("path", ""))
    title = intent.get("title", "Untitled")
    body = intent.get("body") or message
    needs_review = intent.get("needs_review", False)
    reason = intent.get("reason", "")

    # Strip leading heading if AI echoed the title as the first line (e.g. "# My Title\n...")
    # to avoid the title appearing twice in the rendered view.
    body_lines = body.strip().splitlines()
    if body_lines and body_lines[0].lstrip("#").strip().lower() == title.strip().lower():
        body = "\n".join(body_lines[1:]).lstrip("\n")

    # Guard: if the AI says update but returned a path that isn't in the existing docs,
    # it hallucinated — fall through to create so content isn't silently discarded.
    candidate_paths = {d["path"] for d in candidate_docs}
    if action == "update" and path and path not in candidate_paths:
        action = "create"

    if action == "update" and path:
        doc = await _update_with_merge(path, title, message, body, session)
        if needs_review and doc:
            doc.status = "needs_review"
            await session.commit()
        return {"action": "update", "path": path, "needs_review": needs_review, "reason": reason, "message": f"Updated doc: {title}."}
    else:
        if not path:
            slug = title.lower().replace(" ", "-")[:40]
            path = f"personal/{slug}.md"
        try:
            doc = await create_doc(path, title, body, [], owner, session)
        except IntegrityError:
            # Path already exists — merge new content into it instead of creating a duplicate
            await session.rollback()
            doc = await _update_with_merge(path, title, message, body, session)
            action = "update"
        if needs_review and doc:
            doc.status = "needs_review"
            await session.commit()
        return {"action": action, "path": path, "needs_review": needs_review, "reason": reason, "message": f"{'Updated' if action == 'update' else 'Created'} doc: {title}."}
