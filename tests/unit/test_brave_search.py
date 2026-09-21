"""Unit tests for BraveSearchProvider."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from deep_research.core.exceptions import ConfigurationError, SearchProviderError
from deep_research.providers.search.brave import BraveSearchProvider
from deep_research.providers.search.factory import get_search_provider

SAMPLE_BRAVE_JSON = {
    "web": {
        "results": [
            {
                "title": "Brave Search - Quantum Computing Breakthrough",
                "url": "https://example.org/quantum-news",
                "description": "Researchers announce a major breakthrough in silicon spin qubits.",
                "page_age": "2026-03-12",
            },
            {
                "title": "Secondary Finding",
                "url": "https://example.org/secondary",
                "description": "Supplemental context regarding quantum architectures.",
                "page_age": "2026-01-10",
            },
        ]
    }
}


class TestBraveSearchProvider:
    def test_factory_registration(self) -> None:
        provider = get_search_provider("brave", api_key="dummy_key")
        assert isinstance(provider, BraveSearchProvider)
        assert provider.provider_name == "brave"
        assert provider.supports_direct_content() is False

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_configuration_error(self) -> None:
        provider = BraveSearchProvider(api_key=None)
        with pytest.raises(ConfigurationError, match="Brave Search API key is missing"):
            await provider.search("test query")

    @pytest.mark.asyncio
    async def test_search_successful_parse(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_BRAVE_JSON
        mock_client.get.return_value = mock_resp

        provider = BraveSearchProvider(api_key="valid_token", client=mock_client)
        resp = await provider.search("quantum computing breakthrough", max_results=5)

        assert resp.query == "quantum computing breakthrough"
        assert len(resp.results) == 2
        first = resp.results[0]
        assert first.title == "Brave Search - Quantum Computing Breakthrough"
        assert first.url == "https://example.org/quantum-news"
        assert "silicon spin qubits" in first.snippet
        assert first.published_date == "2026-03-12"

    @pytest.mark.asyncio
    async def test_search_http_error_handling(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized: Invalid API Key"
        http_err = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_resp
        )
        mock_client.get.side_effect = http_err

        provider = BraveSearchProvider(api_key="bad_token", client=mock_client)
        with pytest.raises(SearchProviderError, match="Brave Search API HTTP 401"):
            await provider.search("query")
