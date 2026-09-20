"""Unit tests for Search provider abstraction, Mock provider, Tavily, and DuckDuckGo."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from deep_research.core.exceptions import ConfigurationError, SearchProviderError
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.search import (
    BaseSearchProvider,
    DuckDuckGoProvider,
    MockSearchProvider,
    TavilyProvider,
    get_search_provider,
    list_search_providers,
)
from deep_research.providers.search.duckduckgo import _extract_real_url


class TestMockSearchProvider:
    @pytest.mark.asyncio
    async def test_synthetic_results_generation(self) -> None:
        provider = MockSearchProvider()
        response = await provider.search("quantum error correction", max_results=3)

        assert isinstance(response, SearchResponse)
        assert response.query == "quantum error correction"
        assert len(response.results) == 3
        assert response.results[0].title.startswith("Mock Study 1")
        assert response.results[0].raw_score is not None
        assert provider.supports_direct_content() is False

    @pytest.mark.asyncio
    async def test_queued_response(self) -> None:
        provider = MockSearchProvider()
        expected = SearchResponse(
            query="test",
            results=[
                SearchResult(
                    title="Custom Title", url="https://custom.org", snippet="Custom snippet"
                )
            ],
            provider_name="mock",
            execution_time_ms=10.0,
        )
        provider.queue_response(expected)

        response = await provider.search("test")
        assert response == expected
        assert response.results[0].title == "Custom Title"

    @pytest.mark.asyncio
    async def test_queued_error_raises(self) -> None:
        provider = MockSearchProvider()
        provider.queue_error(SearchProviderError("Network connection down"))

        with pytest.raises(SearchProviderError, match="Network connection down"):
            await provider.search("failing query")


class TestSearchProviderFactory:
    def test_list_providers(self) -> None:
        providers = list_search_providers()
        assert "mock" in providers
        assert "tavily" in providers
        assert "duckduckgo" in providers

    def test_get_registered_provider(self) -> None:
        provider = get_search_provider("mock", provider_name="custom_mock")
        assert isinstance(provider, BaseSearchProvider)
        assert provider.provider_name == "custom_mock"

    def test_case_insensitive_lookup(self) -> None:
        provider = get_search_provider("TavILY", api_key="tvly-testkey12345678901234567890")
        assert isinstance(provider, TavilyProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="Unknown search provider 'bing'"):
            get_search_provider("bing")


class TestTavilyProvider:
    def test_missing_api_key_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="Tavily API key not configured"):
            TavilyProvider(api_key=None)

    @pytest.mark.asyncio
    async def test_search_success_with_mocked_client(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "Quantum Breakthrough",
                    "url": "https://nature.com/articles/quantum-1",
                    "content": "Clean summary content from Tavily.",
                    "score": 0.98,
                    "published_date": "2025-01-01",
                    "raw_content": "# Full Page Content\nDetails here.",
                }
            ]
        }
        mock_client.post.return_value = mock_resp

        provider = TavilyProvider(api_key="tvly-mockkey12345678901234567890", client=mock_client)
        assert provider.supports_direct_content() is True

        response = await provider.search("quantum", max_results=5)
        assert len(response.results) == 1
        assert response.results[0].title == "Quantum Breakthrough"
        assert response.results[0].direct_markdown == "# Full Page Content\nDetails here."
        assert response.results[0].raw_score == 0.98

    @pytest.mark.asyncio
    async def test_search_401_raises_config_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        error = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_resp)
        mock_resp.raise_for_status.side_effect = error
        mock_client.post.return_value = mock_resp

        provider = TavilyProvider(api_key="tvly-badkey", client=mock_client)
        with pytest.raises(ConfigurationError, match="Invalid Tavily API key"):
            await provider.search("query")


class TestDuckDuckGoProvider:
    def test_extract_real_url(self) -> None:
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget%3Fa%3D1&rut=123"
        assert _extract_real_url(wrapped) == "https://example.com/target?a=1"
        direct = "https://directsite.org/page"
        assert _extract_real_url(direct) == direct

    @pytest.mark.asyncio
    async def test_duckduckgo_parsing_with_mocked_html(self) -> None:
        html_content = """
        <html><body>
        <div class="result">
            <h2 class="result__title">
                <a class="result__a" href="https://arxiv.org/abs/2401.99999">Title of Paper</a>
            </h2>
            <a class="result__snippet">This is the extracted snippet describing the research.</a>
        </div>
        <div class="result">
            <h2 class="result__title">
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnature.com%2Fdoc">Nature Doc</a>
            </h2>
            <a class="result__snippet">Another snippet here.</a>
        </div>
        </body></html>
        """
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.text = html_content
        mock_client.post.return_value = mock_resp

        provider = DuckDuckGoProvider(client=mock_client)
        assert provider.supports_direct_content() is False

        response = await provider.search("test query", max_results=2)
        assert len(response.results) == 2
        assert response.results[0].title == "Title of Paper"
        assert response.results[0].url == "https://arxiv.org/abs/2401.99999"
        assert response.results[1].url == "https://nature.com/doc"
