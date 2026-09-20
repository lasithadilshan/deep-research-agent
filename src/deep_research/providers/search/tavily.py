"""Tavily search provider implementation for agentic web discovery."""

import time
from typing import Any

import httpx

from deep_research.config.settings import get_settings
from deep_research.core.exceptions import ConfigurationError, SearchProviderError
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import register_search_provider

TAVILY_API_ENDPOINT = "https://api.tavily.com/search"


@register_search_provider("tavily")
class TavilyProvider(BaseSearchProvider):
    """Production search provider leveraging Tavily's AI-optimized search API."""

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(provider_name="tavily")
        settings = get_settings()
        self.api_key = api_key or settings.tavily_api_key

        if not self.api_key and client is None:
            raise ConfigurationError(
                "Tavily API key not configured. Set TAVILY_API_KEY environment variable or pass api_key."
            )

        self._client = client

    def supports_direct_content(self) -> bool:
        """Tavily returns clean parsed markdown directly in the snippet/content fields."""
        return True

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        **kwargs: Any,
    ) -> SearchResponse:
        """Execute search via Tavily API and normalize results."""
        start_time = time.perf_counter()
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": kwargs.get("include_raw_content", False),
        }

        try:
            if self._client:
                response = await self._client.post(TAVILY_API_ENDPOINT, json=payload, timeout=15.0)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(TAVILY_API_ENDPOINT, json=payload, timeout=15.0)

            response.raise_for_status()
            data = response.json()

            results: list[SearchResult] = []
            for item in data.get("results", []):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        raw_score=item.get("score"),
                        published_date=item.get("published_date"),
                        direct_markdown=item.get("raw_content") or item.get("content"),
                    )
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SearchResponse(
                query=query,
                results=results,
                provider_name="tavily",
                execution_time_ms=round(elapsed_ms, 2),
                total_results_estimate=len(results),
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 or e.response.status_code == 403:
                raise ConfigurationError(f"Invalid Tavily API key: {e}") from e
            raise SearchProviderError(
                f"Tavily search API error (HTTP {e.response.status_code}): {e}"
            ) from e
        except httpx.RequestError as e:
            raise SearchProviderError(f"Failed to connect to Tavily search API: {e}") from e
        except Exception as e:
            raise SearchProviderError(f"Unexpected error executing Tavily search: {e}") from e
