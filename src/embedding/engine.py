import numpy as np
from ollama import AsyncClient

from src.config import settings

_EMBEDDING_MODEL = "nomic-embed-text"
_EMBEDDING_DIM = 768

_client: AsyncClient | None = None


def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient(host=settings.ollama_host)
    return _client


async def embed_jobs(jobs: list) -> list[list[float]]:
    client = _get_client()
    texts = [f"passage: {j.title} {j.description or ''}" for j in jobs]
    response = await client.embed(model=_EMBEDDING_MODEL, input=texts)
    return [e for e in response["embeddings"]]


async def embed_query(query: str) -> list[float]:
    client = _get_client()
    response = await client.embed(model=_EMBEDDING_MODEL, input=f"query: {query}")
    return response["embeddings"][0]


def rank_jobs(
    query_embedding: list[float],
    job_embeddings: list[list[float]],
    top_k: int = 50,
) -> list[dict]:
    query_vec = np.array(query_embedding)
    corpus = np.array(job_embeddings)
    norms = np.linalg.norm(corpus, axis=1)
    norms = np.where(norms == 0, 1, norms)
    corpus_normed = corpus / norms[:, np.newaxis]
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []
    query_normed = query_vec / query_norm
    scores = corpus_normed @ query_normed
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [{"corpus_id": int(idx), "score": float(scores[idx])} for idx in top_indices]
