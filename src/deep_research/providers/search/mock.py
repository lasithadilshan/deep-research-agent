"""Deterministic Mock search provider for offline testing."""

import time
from typing import Any

from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import register_search_provider


@register_search_provider("mock")
class MockSearchProvider(BaseSearchProvider):
    """Mock search engine returning pre-canned or synthetic results."""

    def __init__(self, provider_name: str = "mock") -> None:
        super().__init__(provider_name=provider_name)
        self.response_queue: list[SearchResponse] = []
        self.error_queue: list[Exception] = []
        self.recorded_queries: list[dict[str, Any]] = []

    def queue_response(self, response: SearchResponse) -> None:
        """Queue a specific response to be returned on next search."""
        self.response_queue.append(response)

    def queue_error(self, exc: Exception) -> None:
        """Queue an exception to be raised on next search."""
        self.error_queue.append(exc)

    def supports_direct_content(self) -> bool:
        return False

    async def search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> SearchResponse:
        self.recorded_queries.append({"query": query, "max_results": max_results, "kwargs": kwargs})

        if self.error_queue:
            raise self.error_queue.pop(0)

        if self.response_queue:
            return self.response_queue.pop(0)

        start_time = time.perf_counter()
        results: list[SearchResult] = []
        for i in range(1, min(max_results + 1, 4)):
            results.append(
                SearchResult(
                    title=f"Mock Study {i} on '{query}'",
                    url=f"https://example.org/research/paper_{i}",
                    snippet=f"Detailed analytical findings regarding {query} from perspective {i}.",
                    raw_score=1.0 - (i * 0.1),
                    published_date="2025-06-15",
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return SearchResponse(
            query=query,
            results=results,
            provider_name=self.provider_name,
            execution_time_ms=round(elapsed_ms, 2),
            total_results_estimate=len(results),
        )
