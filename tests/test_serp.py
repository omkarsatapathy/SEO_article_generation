from unittest.mock import patch

import pytest

from app.graph.state import SerpResult
from app.graph.tools.serp_fetch import get_mock_serp_data, serp_fetch_tool


# ── Integration test (hits real SerpAPI) ──────────────────────────────────────

@pytest.mark.integration
def test_serp_fetch_real_api():
    """Live call to SerpAPI — requires valid SERPAPI_KEY in .env."""
    results = serp_fetch_tool.invoke("best SEO practices 2025")

    assert isinstance(results, list), "result must be a list"
    assert len(results) > 0, "expected at least one result"
    for r in results:
        assert isinstance(r, SerpResult)
        assert r.rank >= 1
        assert r.url.startswith("http")
        assert len(r.title) > 0
    print(f"\n✅ SerpAPI returned {len(results)} real results")
    for r in results:
        print(f"  [{r.rank}] {r.title}\n       {r.url}")


def test_mock_serp_returns_10_results():
    results = get_mock_serp_data("content marketing strategy")
    assert len(results) == 10


def test_mock_serp_results_are_valid_pydantic():
    results = get_mock_serp_data("machine learning") 
    for result in results:
        assert isinstance(result, SerpResult)
        assert result.rank
        assert result.url
        assert result.title
        assert result.snippet


def test_mock_serp_ranks_sequential():
    results = get_mock_serp_data("python api development")
    ranks = [r.rank for r in results]
    assert ranks == list(range(1, 11))


def test_serp_fetch_falls_back_to_mock():
    with patch(
        "app.graph.tools.serp_fetch.requests.get",
        side_effect=ConnectionError("network unreachable"),
    ):
        results = serp_fetch_tool.invoke("seo best practices")

    assert len(results) == 10
    for result in results:
        assert isinstance(result, SerpResult)
        assert result.rank >= 1
        assert result.url.startswith("https://")
