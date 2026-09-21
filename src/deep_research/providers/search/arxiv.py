"""ArXiv academic search provider querying the official ArXiv REST/Atom API."""

import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx

from deep_research.config.logging import get_logger
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import register_search_provider

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@register_search_provider("arxiv")
class ArxivSearchProvider(BaseSearchProvider):
    """Zero-key academic search provider querying the public arXiv API for scientific preprints."""

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        provider_name: str = "arxiv",
    ) -> None:
        super().__init__(provider_name=provider_name)
        self.api_key = api_key
        self._client = client
        self.logger = get_logger("ArxivSearchProvider")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: object,
    ) -> SearchResponse:
        """Query the arXiv API and return normalized academic search results."""
        start_time = time.perf_counter()
        normalized_query = query.strip()

        # Format arXiv search syntax
        encoded_query = quote_plus(f"all:{normalized_query}")
        url = f"{ARXIV_API_URL}?search_query={encoded_query}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"

        headers = {"User-Agent": "DeepResearchAgent/1.0 (academic-research-tool)"}

        try:
            if self._client:
                resp = await self._client.get(url, headers=headers, timeout=15.0)
            else:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers, timeout=15.0)

            resp.raise_for_status()
            results = self._parse_atom_feed(resp.text)
        except Exception as e:
            self.logger.warning("arxiv_search_failed", query=query, error=str(e))
            results = []

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=normalized_query,
            results=results,
            provider_name=self.provider_name,
            execution_time_ms=round(elapsed_ms, 2),
        )

    def supports_direct_content(self) -> bool:
        """Returns False because ArXiv provides metadata; paper bodies are fetched via WebFetcher."""
        return False

    def _parse_atom_feed(self, xml_text: str) -> list[SearchResult]:
        """Parse XML Atom feed from arXiv into normalized SearchResult objects."""
        if not xml_text or not xml_text.strip():
            return []

        results: list[SearchResult] = []
        try:
            root = ET.fromstring(xml_text)
            entries = root.findall("atom:entry", ATOM_NS)

            for rank, entry in enumerate(entries):
                title_elem = entry.find("atom:title", ATOM_NS)
                title = (
                    " ".join(title_elem.text.split())
                    if title_elem is not None and title_elem.text
                    else "Untitled Paper"
                )

                summary_elem = entry.find("atom:summary", ATOM_NS)
                summary = (
                    " ".join(summary_elem.text.split())
                    if summary_elem is not None and summary_elem.text
                    else ""
                )

                published_elem = entry.find("atom:published", ATOM_NS)
                published = published_elem.text if published_elem is not None else None

                # Find direct PDF link if available, fallback to abstract link
                pdf_url: str | None = None
                abs_url: str | None = None

                for link in entry.findall("atom:link", ATOM_NS):
                    rel = link.get("rel")
                    href = link.get("href", "")
                    content_type = link.get("type", "")
                    title_attr = link.get("title", "")

                    if title_attr == "pdf" or content_type == "application/pdf":
                        pdf_url = href
                    elif rel == "alternate":
                        abs_url = href

                # Collect authors
                authors: list[str] = []
                for author_elem in entry.findall("atom:author", ATOM_NS):
                    name_elem = author_elem.find("atom:name", ATOM_NS)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())

                author_str = f"Authors: {', '.join(authors[:5])}. " if authors else ""
                snippet = f"{author_str}{summary}"

                target_url = pdf_url or abs_url or ""
                if not target_url:
                    id_elem = entry.find("atom:id", ATOM_NS)
                    target_url = id_elem.text if id_elem is not None and id_elem.text else ""

                if target_url:
                    results.append(
                        SearchResult(
                            title=title,
                            url=target_url,
                            snippet=snippet,
                            raw_score=round(1.0 - (rank * 0.05), 2),
                            published_date=published,
                        )
                    )
        except Exception as err:
            self.logger.warning("arxiv_xml_parse_error", error=str(err))

        return results
