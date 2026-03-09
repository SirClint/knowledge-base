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


app = FastAPI(title="Knowledge Base API", lifespan=lifespan, docs_url="/api-docs", redoc_url="/api-redoc")


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

# ── Admin routes ──────────────────────────────────────────────────────────────
from admin.router import router as admin_router

app.include_router(admin_router)

# ── Versions routes ───────────────────────────────────────────────────────────
from versions.router import router as versions_router

app.include_router(versions_router)

# ── Comments routes ───────────────────────────────────────────────────────────
from comments.router import router as comments_router

app.include_router(comments_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ai")
async def health_ai():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            if r.status_code == 200:
                return {"ai": "online"}
    except Exception:
        pass
    return {"ai": "offline"}


@app.get("/health/summary")
async def health_summary():
    import httpx
    from sqlalchemy import select, func
    from db.models import Document
    from auth.users import User
    from db.database import async_session_maker
    from scheduler.jobs import get_overdue_docs

    # AI status
    ai_status = "offline"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            if r.status_code == 200:
                ai_status = "online"
    except Exception:
        pass

    # DB counts — use get_overdue_docs for accurate review queue (includes time-overdue docs)
    async with async_session_maker() as session:
        doc_count = (await session.execute(select(func.count()).select_from(Document))).scalar() or 0
        user_count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        review_count = len(await get_overdue_docs(session))

    return {
        "app_version": settings.app_version,
        "doc_count": doc_count,
        "user_count": user_count,
        "review_queue_count": review_count,
        "ai": ai_status,
    }
