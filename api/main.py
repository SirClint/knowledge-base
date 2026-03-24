import time
from collections import defaultdict
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from db.database import create_db
from config import settings
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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


app = FastAPI(
    title="Knowledge Base API",
    lifespan=lifespan,
    docs_url="/api-docs" if settings.enable_api_docs else None,
    redoc_url="/api-redoc" if settings.enable_api_docs else None,
)

# ── Rate Limiting ──────────────────────────────────────────────────────────────
from limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


class _SimpleRateLimiter:
    """Thread-safe in-memory rate limiter for per-IP, per-path limiting."""

    # (method, path) → (max_requests, window_seconds)
    LIMITS: dict[tuple[str, str], tuple[int, int]] = {
        ("POST", "/auth/jwt/login"): (10, 60),
        ("POST", "/auth/register"): (5, 60),
        ("POST", "/ingest/email"): (20, 60),
    }

    def __init__(self):
        self._log: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_req: int, window: int) -> bool:
        now = time.monotonic()
        times = [t for t in self._log[key] if now - t < window]
        self._log[key] = times
        if len(times) >= max_req:
            return False
        self._log[key].append(now)
        return True


_path_limiter = _SimpleRateLimiter()


class PathRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)
        limit_cfg = _SimpleRateLimiter.LIMITS.get((request.method, request.url.path))
        if limit_cfg:
            ip = request.client.host if request.client else "unknown"
            key = f"{ip}:{request.method}:{request.url.path}"
            if not _path_limiter.is_allowed(key, *limit_cfg):
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(PathRateLimitMiddleware)

# ── CORS Policy ────────────────────────────────────────────────────────────────
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Auth routes ───────────────────────────────────────────────────────────────
from auth.users import fastapi_users, auth_backend, UserRead, UserCreate, UserUpdate, current_active_user

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
async def health_ai(user=Depends(current_active_user)):
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
async def health_summary(user=Depends(current_active_user)):
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
