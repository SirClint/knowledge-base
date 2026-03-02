import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base, Document


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s
    await engine.dispose()


async def test_create_document(session):
    doc = Document(
        path="team/processes/deploy.md",
        title="Deploy Process",
        tags='["deployment"]',
        owner="alice",
        status="current",
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    assert doc.id is not None
    assert doc.title == "Deploy Process"
