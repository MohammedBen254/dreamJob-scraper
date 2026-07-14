from __future__ import annotations

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from structlog import get_logger

from src.config import settings

logger = get_logger()

_reranker = None
_executor = ThreadPoolExecutor(max_workers=1)


def _get_reranker():
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        _reranker = TextCrossEncoder(model_name=settings.reranker_model)
        logger.info("reranker_loaded", model=settings.reranker_model)
    return _reranker


async def init_reranker() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _get_reranker)


def rerank_pairs(
    query: str,
    documents: list[str],
) -> list[float]:
    reranker = _get_reranker()
    raw_scores = list(reranker.rerank(query, documents))
    normalized = [1 / (1 + math.exp(-s)) for s in raw_scores]
    return normalized


async def rerank_query_matches(
    query_text: str,
    candidates: list[dict],
    top_k: int | None = None,
) -> list[dict]:
    if not candidates:
        return []

    if top_k is not None:
        candidates = candidates[:top_k]

    documents = [c.get("description", "") or c.get("title", "") for c in candidates]
    loop = asyncio.get_running_loop()
    scores = await loop.run_in_executor(_executor, partial(rerank_pairs, query_text, documents))

    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = round(score * 100, 1)

    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    return candidates