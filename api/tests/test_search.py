import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from search.service import embed_doc, search_semantic
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base, Document


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_embed_doc_calls_ollama():
    with patch("search.service.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        result = await embed_doc("some text about kubernetes")
        assert isinstance(result, list)
        assert len(result) == 3


async def test_search_semantic_returns_results():
    with patch("search.service.get_chroma_collection") as mock_col:
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{"path": "team/processes/deploy.md"}, {"path": "team/architecture/infra.md"}]],
        }
        mock_col.return_value = mock_collection
        with patch("search.service.embed_doc", new=AsyncMock(return_value=[0.1, 0.2])):
            results = await search_semantic("how do I deploy?", n_results=2)
            assert len(results) == 2
            assert results[0]["path"] == "team/processes/deploy.md"


async def test_keyword_search(session):
    from search.service import search_keyword
    doc = Document(path="team/processes/deploy.md", title="Kubernetes Deploy", tags='["kubernetes"]', body_preview="steps to deploy")
    session.add(doc)
    await session.commit()
    results = await search_keyword("kubernetes", session)
    assert any("Kubernetes" in r["title"] for r in results)
