import httpx
import chromadb
from config import settings


def get_chroma_collection():
    client = chromadb.PersistentClient(path=settings.chromadb_path)
    return client.get_or_create_collection("documents")


async def embed_doc(text: str) -> list[float]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=30,
        )
        return response.json()["embedding"]


async def index_doc_vectors(doc_id: str, path: str, text: str):
    embedding = await embed_doc(text)
    collection = get_chroma_collection()
    collection.upsert(
        ids=[doc_id],
        embeddings=[embedding],
        metadatas=[{"path": path}],
    )


async def search_semantic(query: str, n_results: int = 10) -> list[dict]:
    embedding = await embed_doc(query)
    collection = get_chroma_collection()
    results = collection.query(query_embeddings=[embedding], n_results=n_results)
    return [
        {"path": meta["path"], "score": 1 - dist}
        for meta, dist in zip(results["metadatas"][0], results["distances"][0])
    ]


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from db.models import Document


async def search_keyword(query: str, session: AsyncSession) -> list[dict]:
    q = f"%{query}%"
    result = await session.execute(
        select(Document).where(
            or_(Document.title.ilike(q), Document.tags.ilike(q), Document.body_preview.ilike(q))
        )
    )
    docs = result.scalars().all()
    return [{"id": d.id, "path": d.path, "title": d.title, "tags": d.tags} for d in docs]
