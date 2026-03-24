from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from db.database import get_session
from db.models import Document
from docs_.service import create_doc, get_doc, update_doc, delete_doc, _safe_path
from auth.users import require_editor, require_admin, current_active_user
from audit.service import log_event
from config import settings
from ai.service import KNOWN_FOLDERS
import frontmatter

router = APIRouter(prefix="/docs", tags=["docs"])


class DocCreate(BaseModel):
    title: str
    path: str
    body: str
    tags: list[str] = []
    owner: str = ""


class DocUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    status: str | None = None


@router.post("", status_code=201)
async def create(request: Request, payload: DocCreate, session=Depends(get_session), user=Depends(require_editor)):
    owner = payload.owner or user.email
    doc = await create_doc(payload.path, payload.title, payload.body, payload.tags, owner, session)
    await log_event(session, actor_email=user.email, action="doc.create",
                    target=payload.path, ip=request.client.host if request.client else None)
    return {"id": doc.id, "title": doc.title, "path": doc.path}


@router.get("", dependencies=[Depends(current_active_user)])
async def list_all(session=Depends(get_session)):
    from sqlalchemy import select
    result = await session.execute(select(Document))
    docs = result.scalars().all()
    return [{"id": d.id, "path": d.path, "title": d.title} for d in docs]


@router.get("/folders", dependencies=[Depends(current_active_user)])
async def list_folders():
    return KNOWN_FOLDERS


@router.get("/{path:path}")
async def read(path: str, session=Depends(get_session), user=Depends(current_active_user)):
    _safe_path(path)  # guard against path traversal BEFORE file read
    doc = await get_doc(path, session)
    if not doc:
        raise HTTPException(404)
    # Load full body from vault file
    full_path = Path(settings.vault_path) / path
    body = ""
    if full_path.exists():
        post = frontmatter.load(str(full_path))
        body = post.content
    return {
        "id": doc.id, "title": doc.title, "path": doc.path, "body": body,
        "tags": doc.tags, "owner": doc.owner, "status": doc.status,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "created_by": doc.owner or None,
        "updated_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
        "updated_by": doc.updated_by or None,
    }


@router.put("/{path:path}", dependencies=[Depends(require_editor)])
async def update(request: Request, path: str, payload: DocUpdate, session=Depends(get_session), user=Depends(current_active_user)):
    updates = payload.model_dump(exclude_none=True)
    doc = await update_doc(path, updates, session, saved_by=user.email)
    if not doc:
        raise HTTPException(404)
    await log_event(session, actor_email=user.email, action="doc.update",
                    target=path, ip=request.client.host if request.client else None)
    return doc


@router.delete("/{path:path}")
async def delete(request: Request, path: str, session=Depends(get_session), user=Depends(require_admin)):
    ok = await delete_doc(path, session)
    if not ok:
        raise HTTPException(404)
    await log_event(session, actor_email=user.email, action="doc.delete",
                    target=path, ip=request.client.host if request.client else None)
    return {"deleted": True}
