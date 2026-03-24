from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker as _async_sessionmaker
from db.models import Base

_engine = None
_maker = None


def _get_engine():
    global _engine
    if _engine is None:
        from config import settings
        _engine = create_async_engine(settings.database_url)
    return _engine


def _get_maker():
    global _maker
    if _maker is None:
        _maker = _async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _maker


def async_session_maker():
    """Return a new AsyncSession context manager. Usage: async with async_session_maker() as s:"""
    return _get_maker()()


async def create_db():
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        for stmt in [
            "ALTER TABLE documents ADD COLUMN created_at DATETIME",
            "ALTER TABLE documents ADD COLUMN updated_by VARCHAR DEFAULT ''",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[db migration] {stmt!r} skipped: {e}")
        # Backfill created_at from indexed_at for existing rows that predate this column
        await conn.execute(text(
            "UPDATE documents SET created_at = indexed_at WHERE created_at IS NULL AND indexed_at IS NOT NULL"
        ))


async def get_session() -> AsyncSession:
    async with _get_maker()() as session:
        yield session
