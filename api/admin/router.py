import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from db.database import get_session
from auth.users import User, require_admin, get_user_manager
from audit.service import log_event
from db.models import Setting, AuditLog

SETTING_DEFAULTS = {"semantic_threshold": "0.50"}
ALLOWED_SETTINGS = set(SETTING_DEFAULTS.keys())

router = APIRouter(prefix="/admin", tags=["admin"])


class RoleUpdate(BaseModel):
    role: str


class PasswordReset(BaseModel):
    password: str


class SettingUpdate(BaseModel):
    value: str


@router.get("/settings")
async def get_settings(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    result = await session.execute(select(Setting))
    stored = {s.key: s.value for s in result.scalars().all()}
    return {**SETTING_DEFAULTS, **stored}


@router.patch("/settings/{key}")
async def update_setting(
    key: str,
    body: SettingUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    if key not in ALLOWED_SETTINGS:
        raise HTTPException(status_code=400, detail=f"Unknown setting: {key}")
    if key == "semantic_threshold":
        try:
            val = float(body.value)
            if not (0.0 <= val <= 1.0):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="semantic_threshold must be between 0.0 and 1.0")
    setting = await session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=body.value)
        session.add(setting)
    else:
        setting.value = body.value
    await session.commit()
    return {"key": key, "value": body.value}


@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [
        {"id": str(u.id), "email": u.email, "role": u.role, "is_active": u.is_active}
        for u in users
    ]


@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(require_admin),
):
    if body.role not in ("reader", "editor", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if current.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = body.role
    session.add(AuditLog(actor_email=current.email, action="user.role_change", target=str(user_id), detail=body.role))
    await session.commit()
    await session.refresh(user)
    return {"id": str(user.id), "email": user.email, "role": user.role, "is_active": user.is_active}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: uuid.UUID,
    body: PasswordReset,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
    user_manager=Depends(get_user_manager),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    stripped = body.password.strip()
    if len(stripped) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user.hashed_password = user_manager.password_helper.hash(stripped)
    session.add(AuditLog(actor_email=_admin.email, action="user.password_reset", target=str(user_id)))
    await session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(require_admin),
):
    if current.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    session.add(AuditLog(actor_email=current.email, action="user.delete", target=str(user_id)))
    await session.commit()


@router.get("/audit-log")
async def get_audit_log(
    page: int = 1,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    offset = (page - 1) * limit
    total = (await session.execute(select(func.count()).select_from(AuditLog))).scalar() or 0
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
    )
    items = result.scalars().all()
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "actor_email": row.actor_email,
                "action": row.action,
                "target": row.target,
                "detail": row.detail,
                "ip_address": row.ip_address,
            }
            for row in items
        ],
    }
