from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db.database import get_session
from docs_.service import create_doc, get_doc, update_doc, delete_doc
from auth.users import require_editor, require_admin, current_active_user

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


@router.post("", status_code=201, dependencies=[Depends(require_editor)])
async def create(payload: DocCreate, session=Depends(get_session)):
    doc = await create_doc(payload.path, payload.title, payload.body, payload.tags, payload.owner, session)
    return {"id": doc.id, "title": doc.title, "path": doc.path}


@router.get("/{path:path}")
async def read(path: str, session=Depends(get_session), user=Depends(current_active_user)):
    doc = await get_doc(path, session)
    if not doc:
        raise HTTPException(404)
    return doc


@router.put("/{path:path}", dependencies=[Depends(require_editor)])
async def update(path: str, payload: DocUpdate, session=Depends(get_session)):
    updates = payload.model_dump(exclude_none=True)
    doc = await update_doc(path, updates, session)
    if not doc:
        raise HTTPException(404)
    return doc


@router.delete("/{path:path}", dependencies=[Depends(require_admin)])
async def delete(path: str, session=Depends(get_session)):
    ok = await delete_doc(path, session)
    if not ok:
        raise HTTPException(404)
    return {"deleted": True}
