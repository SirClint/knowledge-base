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


async def test_needs_review_docs_included_in_queue(session):
    flagged = Document(
        path="personal/ai-note.md", title="AI Note",
        last_reviewed=None, status="needs_review"
    )
    session.add(flagged)
    await session.commit()
    results = await get_overdue_docs(session)
    paths = [r.path for r in results]
    assert "personal/ai-note.md" in paths


async def test_overdue_docs_not_affected_by_change(session):
    overdue = Document(
        path="team/processes/old2.md", title="Old Doc 2",
        last_reviewed=str(date.today() - timedelta(days=60)),
        review_interval="30d", status="current"
    )
    session.add(overdue)
    await session.commit()
    results = await get_overdue_docs(session)
    paths = [r.path for r in results]
    assert "team/processes/old2.md" in paths
