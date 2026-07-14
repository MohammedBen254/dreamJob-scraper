import pytest
from unittest.mock import patch, AsyncMock


class FakeJob:
    def __init__(self, title, description):
        self.title = title
        self.description = description


@pytest.fixture(autouse=True)
def mock_ollama():
    with patch("src.embedding.engine.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        mock_client_cls.return_value = instance
        instance.embed = AsyncMock(return_value={"embeddings": [[0.1] * 768]})
        yield instance


@pytest.mark.asyncio
async def test_embed_query_returns_list():
    from src.embedding.engine import embed_query

    vec = await embed_query("data analyst python")
    assert isinstance(vec, list)
    assert len(vec) == 768


@pytest.mark.asyncio
async def test_embed_jobs_returns_list():
    from src.embedding.engine import embed_jobs

    jobs = [FakeJob("Data Analyst", "Python SQL Tableau")]
    vecs = await embed_jobs(jobs)
    assert isinstance(vecs, list)
    assert len(vecs) == 1
    assert len(vecs[0]) == 768


def test_rank_jobs_returns_sorted():
    from src.embedding.engine import rank_jobs

    query = [0.9] + [0.1] * 767
    jobs = [
        [0.9] + [0.1] * 767,
        [0.1] * 768,
    ]
    results = rank_jobs(query, jobs, top_k=2)
    assert len(results) == 2
    assert results[0]["corpus_id"] == 0
    assert results[0]["score"] > results[1]["score"]
