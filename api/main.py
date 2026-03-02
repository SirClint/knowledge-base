from fastapi import FastAPI
from contextlib import asynccontextmanager
from db.database import create_db
from config import settings
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db()
    # Index vault on startup
    from db.database import async_session_maker
    from watcher.watcher import index_vault
    async with async_session_maker() as session:
        await index_vault(Path(settings.vault_path), session)
    # Start nightly staleness scheduler
    from scheduler.jobs import run_staleness_check
    scheduler.add_job(run_staleness_check, "cron", hour=2)
    scheduler.start()
    yield
    scheduler.shutdown()


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

# ── Docs routes ───────────────────────────────────────────────────────────────
from docs_.router import router as docs_router

app.include_router(docs_router)

# ── Search routes ─────────────────────────────────────────────────────────────
from search.router import router as search_router

app.include_router(search_router)

# ── Review routes ─────────────────────────────────────────────────────────────
from review.router import router as review_router

app.include_router(review_router)

# ── Ingestion routes ──────────────────────────────────────────────────────────
from ingestion.router import router as ingest_router

app.include_router(ingest_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
