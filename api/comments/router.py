from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from db.database import get_session
from db.models import Comment
from auth.users import current_active_user, User

router = APIRouter(prefix="/comments", tags=["comments"])


class CommentCreate(BaseModel):
    body: str


@router.get("/{path:path}")
async def list_comments(path: str, session: AsyncSession = Depends(get_session), _=Depends(current_active_user)):
    result = await session.execute(
        select(Comment)
        .where(Comment.doc_path == path)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()
    return [
        {"id": c.id, "body": c.body, "author_email": c.author_email, "created_at": c.created_at.isoformat() if c.created_at else ""}
        for c in comments
    ]


@router.post("/{path:path}", status_code=201)
async def add_comment(
    path: str,
    payload: CommentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    if len(payload.body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Comment body cannot be empty")
    if len(payload.body) > 2000:
        raise HTTPException(status_code=400, detail="Comment must be 2000 characters or fewer")
    comment = Comment(doc_path=path, body=payload.body, author_email=user.email)
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return {
        "id": comment.id,
        "body": comment.body,
        "author_email": comment.author_email,
        "created_at": comment.created_at.isoformat() if comment.created_at else ""
    }


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    comment = await session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    # Author can delete own comment; editors and admins can delete any
    if comment.author_email != user.email and user.role not in ("editor", "admin"):
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
    await session.delete(comment)
    await session.commit()
