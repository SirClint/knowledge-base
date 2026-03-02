import pytest
from datetime import date, timedelta
from db.models import Document
from scheduler.jobs import get_overdue_docs
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_overdue_docs_returned(session):
    overdue = Document(
        path="team/processes/old.md", title="Old Doc",
        last_reviewed=str(date.today() - timedelta(days=60)),
        review_interval="30d", status="current"
    )
    current = Document(
        path="team/processes/new.md", title="New Doc",
        last_reviewed=str(date.today() - timedelta(days=5)),
        review_interval="30d", status="current"
    )
    session.add_all([overdue, current])
    await session.commit()
    results = await get_overdue_docs(session)
    paths = [r.path for r in results]
    assert "team/processes/old.md" in paths
    assert "team/processes/new.md" not in paths
