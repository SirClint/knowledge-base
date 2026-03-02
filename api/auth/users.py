from typing import Optional
from fastapi import Depends, HTTPException
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy import Column, String
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Base
from db.database import get_session
from config import settings
import uuid


# ── User model ────────────────────────────────────────────────────────────────

class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"
    role = Column(String, default="reader")  # reader | editor | admin


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserRead(schemas.BaseUser[uuid.UUID]):
    role: str


class UserCreate(schemas.BaseUserCreate):
    role: str = "reader"


class UserUpdate(schemas.BaseUserUpdate):
    role: Optional[str] = None


# ── DB adapter ────────────────────────────────────────────────────────────────

async def get_user_db(session: AsyncSession = Depends(get_session)):
    yield SQLAlchemyUserDatabase(session, User)


# ── User manager ──────────────────────────────────────────────────────────────

SECRET = settings.secret_key


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request=None):
        pass


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


# ── Auth backend ──────────────────────────────────────────────────────────────

bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)


# ── Role-based access ─────────────────────────────────────────────────────────

def require_role(*roles: str):
    async def check(user: User = Depends(current_active_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check


require_editor = require_role("editor", "admin")
require_admin = require_role("admin")
