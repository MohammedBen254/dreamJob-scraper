import pytest
from unittest.mock import patch, MagicMock
import math


def _make_mock_reranker(raw_scores):
    mock_reranker = MagicMock()

    def _rerank_side_effect(query, documents):
        n = len(documents)
        return raw_scores[:n] + [0.0] * max(0, n - len(raw_scores))

    mock_reranker.rerank.side_effect = _rerank_side_effect
    return mock_reranker


@pytest.mark.asyncio
async def test_rerank_query_matches_empty_candidates():
    from src.reranker.engine import rerank_query_matches

    result = await rerank_query_matches("python developer", [])
    assert result == []


def test_rerank_pairs_returns_normalized_scores():
    from src.reranker.engine import rerank_pairs

    mock_reranker = _make_mock_reranker([2.0, -1.0, 0.0])

    with patch("src.reranker.engine._get_reranker", return_value=mock_reranker):
        scores = rerank_pairs("python developer", ["job1", "job2", "job3"])

    assert len(scores) == 3
    assert 0.0 < scores[0] < 1.0
    assert 0.0 < scores[1] < 1.0
    assert 0.0 < scores[2] < 1.0
    expected_0 = 1 / (1 + math.exp(-2.0))
    expected_1 = 1 / (1 + math.exp(1.0))
    expected_2 = 1 / (1 + math.exp(0.0))
    assert abs(scores[0] - expected_0) < 1e-6
    assert abs(scores[1] - expected_1) < 1e-6
    assert abs(scores[2] - expected_2) < 1e-6


def test_rerank_pairs_positive_logit_high_score():
    from src.reranker.engine import rerank_pairs

    mock_reranker = _make_mock_reranker([5.0])

    with patch("src.reranker.engine._get_reranker", return_value=mock_reranker):
        scores = rerank_pairs("query", ["doc"])

    assert scores[0] > 0.99


def test_rerank_pairs_negative_logit_low_score():
    from src.reranker.engine import rerank_pairs

    mock_reranker = _make_mock_reranker([-5.0])

    with patch("src.reranker.engine._get_reranker", return_value=mock_reranker):
        scores = rerank_pairs("query", ["doc"])

    assert scores[0] < 0.01


@pytest.mark.asyncio
async def test_rerank_query_matches_adds_rerank_score():
    from src.reranker.engine import rerank_query_matches

    candidates = [
        {"title": "Data Analyst", "description": "Python SQL Tableau"},
        {"title": "Optics Sales", "description": "Vendeuse optique Casablanca"},
    ]

    mock_reranker = _make_mock_reranker([3.0, -2.0])

    with patch("src.reranker.engine._get_reranker", return_value=mock_reranker):
        result = await rerank_query_matches("data analyst python", candidates)

    assert len(result) == 2
    assert "rerank_score" in result[0]
    assert "rerank_score" in result[1]
    assert result[0]["rerank_score"] > result[1]["rerank_score"]


@pytest.mark.asyncio
async def test_rerank_query_matches_respects_top_k():
    from src.reranker.engine import rerank_query_matches

    candidates = [
        {"title": f"Job {i}", "description": f"Desc {i}"} for i in range(5)
    ]

    mock_reranker = _make_mock_reranker([float(i) for i in range(5)])

    with patch("src.reranker.engine._get_reranker", return_value=mock_reranker):
        result = await rerank_query_matches("query", candidates, top_k=2)

    assert len(result) == 2


def test_reranker_lazy_initialization():
    from src.reranker.engine import _get_reranker

    with patch("fastembed.rerank.cross_encoder.TextCrossEncoder") as mock_cls:
        mock_cls.return_value = MagicMock()
        import src.reranker.engine as engine
        engine._reranker = None
        _reranker1 = _get_reranker()
        _reranker2 = _get_reranker()
        assert mock_cls.call_count == 1