"""Unit tests for ArxivSearchProvider."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from deep_research.providers.search.arxiv import ArxivSearchProvider
from deep_research.providers.search.factory import get_search_provider

SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title type="html">arXiv Query</title>
  <id>http://arxiv.org/api/query</id>
  <updated>2026-09-21T00:00:00Z</updated>
  <entry>
    <id>http://arxiv.org/abs/2403.01234v1</id>
    <updated>2024-03-05T12:00:00Z</updated>
    <published>2024-03-05T12:00:00Z</published>
    <title>Fault-Tolerant Quantum Error Correction with Surface Codes</title>
    <summary>We demonstrate a 99.9% fidelity threshold in logical qubits using rotated surface codes.</summary>
    <author>
      <name>Alice Cooper</name>
    </author>
    <author>
      <name>Bob Dylan</name>
    </author>
    <link href="http://arxiv.org/abs/2403.01234v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2403.01234v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


class TestArxivSearchProvider:
    def test_factory_registration(self) -> None:
        provider = get_search_provider("arxiv")
        assert isinstance(provider, ArxivSearchProvider)
        assert provider.provider_name == "arxiv"
        assert provider.supports_direct_content() is False

    @pytest.mark.asyncio
    async def test_search_successful_parse(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_ARXIV_XML
        mock_client.get.return_value = mock_resp

        provider = ArxivSearchProvider(client=mock_client)
        resp = await provider.search("surface codes quantum", max_results=5)

        assert resp.query == "surface codes quantum"
        assert len(resp.results) == 1
        first = resp.results[0]
        assert "Fault-Tolerant Quantum Error Correction" in first.title
        assert first.url == "http://arxiv.org/pdf/2403.01234v1"
        assert "Alice Cooper, Bob Dylan" in first.snippet
        assert "99.9% fidelity" in first.snippet
        assert first.published_date == "2024-03-05T12:00:00Z"

    @pytest.mark.asyncio
    async def test_search_http_error_graceful_fallback(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")

        provider = ArxivSearchProvider(client=mock_client)
        resp = await provider.search("error query", max_results=3)

        assert resp.query == "error query"
        assert len(resp.results) == 0

    def test_empty_xml_parse(self) -> None:
        provider = ArxivSearchProvider()
        results = provider._parse_atom_feed("")
        assert results == []

        results_bad = provider._parse_atom_feed("not valid xml")
        assert results_bad == []
