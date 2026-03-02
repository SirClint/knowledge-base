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


async def get_session() -> AsyncSession:
    async with _get_maker()() as session:
        yield session
