"""Abstract base protocol for web and academic search providers."""

from abc import ABC, abstractmethod
from typing import Any

from deep_research.models.search import SearchResponse


class BaseSearchProvider(ABC):
    """Abstract interface defining the contract for search providers."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> SearchResponse:
        """Execute search query and return normalized SearchResponse."""
        pass

    @abstractmethod
    def supports_direct_content(self) -> bool:
        """Return True if provider delivers pre-extracted page markdown/content (e.g. Tavily)."""
        pass
