"""Unit tests for ResearchCache SQLite caching engine and integrations."""

from pathlib import Path

import pytest

from deep_research.models.search import SearchResponse, SearchResult
from deep_research.storage.cache import ResearchCache
from deep_research.tools.web_fetcher import WebFetcher


def test_cache_init_and_basic_kv() -> None:
    cache = ResearchCache(db_path=":memory:")
    assert cache.count() == 0

    cache.set(namespace="test", raw_key="key1", payload="hello world")
    assert cache.count() == 1
    assert cache.count(namespace="test") == 1
    assert cache.get(namespace="test", raw_key="key1") == "hello world"

    # Non-existent key
    assert cache.get(namespace="test", raw_key="missing") is None

    # Delete
    deleted = cache.delete(namespace="test", raw_key="key1")
    assert deleted is True
    assert cache.get(namespace="test", raw_key="key1") is None
    assert cache.count() == 0
    cache.close()


def test_cache_ttl_expiration() -> None:
    cache = ResearchCache(db_path=":memory:")
    # Set with negative TTL so it is already expired
    cache.set(namespace="test", raw_key="expired_key", payload="stale data", ttl_hours=-1.0)

    # get() should detect expiration, delete it, and return None
    assert cache.get(namespace="test", raw_key="expired_key") is None

    # Set another expired item and verify purge_expired
    cache.set(namespace="test", raw_key="exp1", payload="val1", ttl_hours=-0.5)
    cache.set(namespace="test", raw_key="exp2", payload="val2", ttl_hours=-0.5)
    cache.set(namespace="test", raw_key="live", payload="val3", ttl_hours=1.0)

    purged = cache.purge_expired()
    assert purged == 2
    assert cache.count() == 1
    assert cache.get(namespace="test", raw_key="live") == "val3"
    cache.close()


def test_cache_search_response_serialization() -> None:
    cache = ResearchCache(db_path=":memory:")

    hit = SearchResult(
        title="AI Research 2026",
        url="https://arxiv.org/abs/2601.12345",
        snippet="Groundbreaking reasoning paradigms.",
        raw_score=0.98,
        published_date="2026-01-10",
    )
    original_resp = SearchResponse(
        query="autonomous AI deep research",
        results=[hit],
        provider_name="tavily",
        execution_time_ms=120.5,
    )

    # Cache response
    cache.set_search(
        provider="tavily",
        query="autonomous AI deep research",
        max_results=5,
        response=original_resp,
    )

    # Query matching
    retrieved = cache.get_search(
        provider="tavily",
        query="autonomous AI deep research",
        max_results=5,
    )
    assert retrieved is not None
    assert retrieved.query == "autonomous AI deep research"
    assert len(retrieved.results) == 1
    assert retrieved.results[0].title == "AI Research 2026"
    assert retrieved.results[0].url == "https://arxiv.org/abs/2601.12345"

    # Query with case insensitivity and whitespace trimming
    retrieved_case = cache.get_search(
        provider="tavily",
        query="  Autonomous AI Deep Research  ",
        max_results=5,
    )
    assert retrieved_case is not None

    # Different provider or max_results should miss
    assert (
        cache.get_search(provider="duckduckgo", query="autonomous AI deep research", max_results=5)
        is None
    )
    assert (
        cache.get_search(provider="tavily", query="autonomous AI deep research", max_results=10)
        is None
    )
    cache.close()


def test_cache_web_content_with_canonical_url() -> None:
    cache = ResearchCache(db_path=":memory:")

    raw_url = "https://example.com/article?utm_source=twitter&ref=newsletter#top"
    cleaned_url = "https://example.com/article"
    html_content = "<html><body><h1>Scientific Breakthrough</h1></body></html>"

    cache.set_web(raw_url, html_content)

    # Should hit with either raw URL (with tracking params) or clean URL
    assert cache.get_web(raw_url) == html_content
    assert cache.get_web(cleaned_url) == html_content
    assert cache.get_web("https://example.com/other") is None
    cache.close()


def test_cache_clear_namespaces() -> None:
    cache = ResearchCache(db_path=":memory:")
    cache.set(namespace="ns1", raw_key="k1", payload="p1")
    cache.set(namespace="ns1", raw_key="k2", payload="p2")
    cache.set(namespace="ns2", raw_key="k3", payload="p3")

    assert cache.count() == 3
    deleted = cache.clear(namespace="ns1")
    assert deleted == 2
    assert cache.count() == 1
    assert cache.get(namespace="ns2", raw_key="k3") == "p3"

    cache.clear()
    assert cache.count() == 0
    cache.close()


def test_cache_disk_persistence(tmp_path: Path) -> None:
    db_file = tmp_path / "subdir" / "persistent_cache.db"
    cache1 = ResearchCache(db_path=db_file)
    cache1.set(namespace="disk", raw_key="item1", payload="stored on disk")
    cache1.close()

    # Reopen same database file
    cache2 = ResearchCache(db_path=db_file)
    assert cache2.get(namespace="disk", raw_key="item1") == "stored on disk"
    cache2.close()


@pytest.mark.asyncio
async def test_web_fetcher_uses_cache() -> None:
    cache = ResearchCache(db_path=":memory:")
    cache.set_web("https://cached-site.example.com/page", "<html>Cached Content</html>")

    # Fetcher should return cached content without performing network requests
    fetcher = WebFetcher(cache=cache)
    content = await fetcher.fetch("https://cached-site.example.com/page?utm_campaign=tracker")
    assert content == "<html>Cached Content</html>"
    cache.close()
