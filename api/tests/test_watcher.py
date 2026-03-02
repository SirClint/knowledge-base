import pytest
from pathlib import Path
import tempfile, os
from unittest.mock import AsyncMock, patch
from watcher.watcher import index_file, index_vault
from db.models import Document
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


SAMPLE = """\
---
title: Test Doc
tags: [test]
owner: bob
status: current
---
Body content here.
"""


async def test_index_file_creates_record(session):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE)
        path = Path(f.name)
    try:
        with patch("search.service.index_doc_vectors", new=AsyncMock()):
            await index_file(path, session)
        from sqlalchemy import select
        result = await session.execute(select(Document).where(Document.title == "Test Doc"))
        doc = result.scalar_one_or_none()
        assert doc is not None
        assert doc.owner == "bob"
    finally:
        os.unlink(path)


async def test_index_file_updates_existing(session):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE)
        path = Path(f.name)
    try:
        with patch("search.service.index_doc_vectors", new=AsyncMock()):
            await index_file(path, session)
            updated = SAMPLE.replace("title: Test Doc", "title: Updated Doc")
            path.write_text(updated)
            await index_file(path, session)
        from sqlalchemy import select, func
        result = await session.execute(select(func.count()).select_from(Document))
        count = result.scalar()
        assert count == 1  # updated, not duplicated
    finally:
        os.unlink(path)
