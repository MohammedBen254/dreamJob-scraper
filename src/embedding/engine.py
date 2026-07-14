import numpy as np
from ollama import AsyncClient
from structlog import get_logger

from src.config import settings

logger = get_logger()

_EMBEDDING_MODEL = "nomic-embed-text"
_EMBEDDING_DIM = 768
_EMBED_BATCH_SIZE = 16
_CHUNK_CHAR_LIMIT = 1500


def _chunk_text(text: str, max_chars: int = _CHUNK_CHAR_LIMIT) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start:
                end = boundary
            else:
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


_client: AsyncClient | None = None


def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        logger.info("ollama_client_init", host=settings.ollama_host)
        _client = AsyncClient(host=settings.ollama_host)
    return _client


async def embed_jobs(jobs: list) -> list[list[float]]:
    client = _get_client()
    job_texts = [f"passage: {j.title} {j.description or ''}" for j in jobs]
    all_chunks: list[str] = []
    job_chunk_counts: list[int] = []

    for text in job_texts:
        chunks = _chunk_text(text)
        all_chunks.extend(chunks)
        job_chunk_counts.append(len(chunks))

    logger.info("embed_jobs_start", model=_EMBEDDING_MODEL, jobs=len(jobs), chunks=len(all_chunks), batch_size=_EMBED_BATCH_SIZE)

    chunk_embeddings: list[list[float]] = []
    for i in range(0, len(all_chunks), _EMBED_BATCH_SIZE):
        batch = all_chunks[i : i + _EMBED_BATCH_SIZE]
        logger.info("embed_batch", batch=i // _EMBED_BATCH_SIZE + 1, size=len(batch))
        try:
            response = await client.embed(model=_EMBEDDING_MODEL, input=batch)
            chunk_embeddings.extend([e for e in response["embeddings"]])
        except Exception as e:
            logger.error("embed_batch_failed", batch=i // _EMBED_BATCH_SIZE + 1, size=len(batch), error=str(e))
            raise

    job_embeddings: list[list[float]] = []
    offset = 0
    for count in job_chunk_counts:
        job_chunks = chunk_embeddings[offset : offset + count]
        avg = np.mean(job_chunks, axis=0).tolist()
        job_embeddings.append(avg)
        offset += count

    logger.info("embed_jobs_done", count=len(job_embeddings), dim=len(job_embeddings[0]) if job_embeddings else 0)
    return job_embeddings


async def embed_query(query: str) -> list[float]:
    client = _get_client()
    logger.info("embed_query_start", model=_EMBEDDING_MODEL, query=query[:80])
    try:
        response = await client.embed(model=_EMBEDDING_MODEL, input=f"query: {query}")
        vec = response["embeddings"][0]
        logger.info("embed_query_done", dim=len(vec))
        return vec
    except Exception as e:
        logger.error("embed_query_failed", model=_EMBEDDING_MODEL, query=query[:80], error=str(e))
        raise


async def embed_text(text: str) -> list[float]:
    client = _get_client()
    chunks = _chunk_text(f"passage: {text}")
    logger.info("embed_text_start", chunks=len(chunks), text_len=len(text))
    chunk_embeddings: list[list[float]] = []
    for i in range(0, len(chunks), _EMBED_BATCH_SIZE):
        batch = chunks[i : i + _EMBED_BATCH_SIZE]
        try:
            response = await client.embed(model=_EMBEDDING_MODEL, input=batch)
            chunk_embeddings.extend([e for e in response["embeddings"]])
        except Exception as e:
            logger.error("embed_text_batch_failed", error=str(e))
            raise
    if len(chunk_embeddings) == 1:
        return chunk_embeddings[0]
    avg = np.mean(chunk_embeddings, axis=0).tolist()
    return avg


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
