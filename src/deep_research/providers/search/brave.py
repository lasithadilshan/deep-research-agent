"""Brave Search provider utilizing the Brave Web Search REST API."""

import time
from typing import Any

import httpx

from deep_research.config.logging import get_logger
from deep_research.core.exceptions import ConfigurationError, SearchProviderError
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import register_search_provider

BRAVE_SEARCH_API_URL = "https://api.search.brave.com/res/v1/web/search"


@register_search_provider("brave")
class BraveSearchProvider(BaseSearchProvider):
    """Brave Web Search API provider for privacy-preserving web search."""

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        provider_name: str = "brave",
        **kwargs: Any,
    ) -> None:
        super().__init__(provider_name=provider_name)
        self.api_key = api_key
        self._client = client
        self.logger = get_logger("BraveSearchProvider")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: object,
    ) -> SearchResponse:
        """Execute a query against the Brave Web Search API."""
        if not self.api_key:
            raise ConfigurationError(
                "Brave Search API key is missing. Set BRAVE_SEARCH_API_KEY in your environment."
            )

        start_time = time.perf_counter()
        normalized_query = query.strip()
        count = min(max_results, 20)

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
            "User-Agent": "DeepResearchAgent/1.0",
        }
        params: dict[str, str | int] = {
            "q": normalized_query,
            "count": count,
        }

        try:
            if self._client:
                resp = await self._client.get(
                    BRAVE_SEARCH_API_URL, headers=headers, params=params, timeout=15.0
                )
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        BRAVE_SEARCH_API_URL, headers=headers, params=params, timeout=15.0
                    )

            resp.raise_for_status()
            data = resp.json()
            results = self._parse_results(data)
        except httpx.HTTPStatusError as e:
            raise SearchProviderError(
                f"Brave Search API HTTP {e.response.status_code}: {e.response.text}"
            ) from e
        except Exception as e:
            self.logger.warning("brave_search_failed", query=query, error=str(e))
            results = []

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=normalized_query,
            results=results,
            provider_name=self.provider_name,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def supports_direct_content(self) -> bool:
        """Returns False because Brave Search returns snippets rather than full page markdown."""
        return False

    def _parse_results(self, data: dict[str, Any]) -> list[SearchResult]:
        """Map Brave Search JSON response to SearchResult list."""
        web_section = data.get("web", {})
        raw_results = web_section.get("results", [])

        results: list[SearchResult] = []
        for rank, item in enumerate(raw_results):
            url = item.get("url")
            title = item.get("title", "")
            snippet = item.get("description", "")
            published = item.get("page_age")

            if url and title:
                results.append(
                    SearchResult(
                        title=title.strip(),
                        url=url.strip(),
                        snippet=snippet.strip() if snippet else "",
                        raw_score=round(1.0 - (rank * 0.05), 2),
                        published_date=str(published) if published else None,
                    )
                )

        return results
