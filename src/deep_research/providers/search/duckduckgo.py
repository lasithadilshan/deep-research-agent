"""Zero-configuration DuckDuckGo search provider fallback."""

import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from deep_research.core.exceptions import SearchProviderError
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import register_search_provider

DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}


def _extract_real_url(href: str) -> str:
    """Unwrap DuckDuckGo redirect wrapper URL if present."""
    if "uddg=" in href:
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        if "uddg" in params:
            return unquote(params["uddg"][0])
    return href


@register_search_provider("duckduckgo")
class DuckDuckGoProvider(BaseSearchProvider):
    """Free, zero-API-key search provider fallback for local development and testing."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        provider_name: str = "duckduckgo",
    ) -> None:
        super().__init__(provider_name=provider_name)
        self._client = client

    def supports_direct_content(self) -> bool:
        return False

    async def search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> SearchResponse:
        """Fetch search results from DuckDuckGo HTML endpoint without requiring API keys."""
        start_time = time.perf_counter()
        data = {"q": query, "b": ""}

        try:
            if self._client:
                response = await self._client.post(
                    DUCKDUCKGO_HTML_URL, data=data, headers=HEADERS, timeout=15.0
                )
            else:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    response = await client.post(
                        DUCKDUCKGO_HTML_URL, data=data, headers=HEADERS, timeout=15.0
                    )

            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            result_elements = soup.find_all("div", class_="result")

            results: list[SearchResult] = []
            for element in result_elements:
                title_elem = element.find("a", class_="result__a")
                snippet_elem = element.find("a", class_="result__snippet")

                if not title_elem:
                    continue

                raw_href = str(title_elem.get("href") or "")
                url = _extract_real_url(raw_href)
                title = title_elem.get_text(strip=True)
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                if url.startswith("http"):
                    results.append(
                        SearchResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                        )
                    )
                if len(results) >= max_results:
                    break

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return SearchResponse(
                query=query,
                results=results,
                provider_name=self.provider_name,
                execution_time_ms=round(elapsed_ms, 2),
                total_results_estimate=len(results),
            )

        except httpx.RequestError as e:
            raise SearchProviderError(f"DuckDuckGo network request failed: {e}") from e
        except Exception as e:
            raise SearchProviderError(f"Error parsing DuckDuckGo search results: {e}") from e
