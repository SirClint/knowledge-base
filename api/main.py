from fastapi import FastAPI
from contextlib import asynccontextmanager
from db.database import create_db
from config import settings
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db()
    # Index vault on startup
    from db.database import async_session_maker
    from watcher.watcher import index_vault
    async with async_session_maker() as session:
        await index_vault(Path(settings.vault_path), session)
    yield


app = FastAPI(title="Knowledge Base API", lifespan=lifespan)


# ── Auth routes ───────────────────────────────────────────────────────────────
from auth.users import fastapi_users, auth_backend, UserRead, UserCreate, UserUpdate

app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Placeholder routes (replaced by routers in later tasks) ──────────────────
from fastapi import Depends
from auth.users import require_editor


@app.post("/docs", status_code=201, dependencies=[Depends(require_editor)])
async def _docs_stub():
    """Stub replaced by docs router in Task 7."""
    return {}
