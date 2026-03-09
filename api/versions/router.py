from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.database import get_session
from db.models import DocVersion
from auth.users import current_active_user, require_editor, User
from docs_.service import get_doc, update_doc
from pathlib import Path
from config import settings
import frontmatter

router = APIRouter(prefix="/versions", tags=["versions"])


@router.get("/{path:path}")
async def list_versions(path: str, session: AsyncSession = Depends(get_session), _=Depends(current_active_user)):
    result = await session.execute(
        select(DocVersion)
        .where(DocVersion.doc_path == path)
        .order_by(DocVersion.saved_at.desc())
    )
    versions = result.scalars().all()
    return [
        {"id": v.id, "saved_by": v.saved_by, "saved_at": str(v.saved_at)}
        for v in versions
    ]


@router.post("/{path:path}/restore/{version_id}")
async def restore_version(
    path: str,
    version_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_editor),
):
    version = await session.get(DocVersion, version_id)
    if not version or version.doc_path != path:
        raise HTTPException(status_code=404, detail="Version not found")

    doc = await get_doc(path, session)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Snapshot current state before restoring (so restore is itself reversible)
    full_path = Path(settings.vault_path) / path
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        current_snapshot = DocVersion(doc_path=path, body=post.content, saved_by=user.email)
        session.add(current_snapshot)

    # Write the restored body via update_doc (which will snapshot again — that's OK, it creates a restore trail)
    await update_doc(path, {"body": version.body}, session, saved_by=user.email)
    return {"restored": True, "path": path}
