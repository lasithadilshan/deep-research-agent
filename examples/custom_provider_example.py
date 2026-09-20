"""Example demonstrating how to register a custom search provider and run research."""

import asyncio

from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models.plan import ResearchMode
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.providers.llm.mock import MockLLMProvider
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import register_search_provider


@register_search_provider("in_house_archive")
class InHouseArchiveSearchProvider(BaseSearchProvider):
    """Custom search provider integrating an internal knowledge base or private archive."""

    def __init__(self, provider_name: str = "in_house_archive") -> None:
        super().__init__(provider_name=provider_name)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        **kwargs: object,
    ) -> SearchResponse:
        # Simulate returning primary technical documents from a proprietary archive
        results = [
            SearchResult(
                title="Internal Laboratory Benchmark: Perovskite Tandem Cells 2026",
                url="https://internal-docs.lab.example.org/reports/perovskite-2026",
                snippet="Internal tests confirmed 34.1% efficiency on monolithic tandem architectures.",
                direct_markdown=(
                    "Under certified lab testing protocols, our research division verified a monolithic "
                    "perovskite-silicon tandem solar cell achieving an efficiency of 34.1% with robust encapsulation."
                ),
                raw_score=0.99,
            )
        ]
        return SearchResponse(
            query=query,
            results=results,
            provider_name=self.provider_name,
            execution_time_ms=15.0,
        )

    def supports_direct_content(self) -> bool:
        return True


async def main() -> None:
    custom_search = InHouseArchiveSearchProvider()
    mock_llm = MockLLMProvider()

    orchestrator = ResearchOrchestrator(
        llm=mock_llm,
        search_provider=custom_search,
    )

    state = await orchestrator.execute_research(
        query="Perovskite tandem efficiency benchmarks",
        mode=ResearchMode.QUICK,
    )

    print(f"Research Completed with Provider: {custom_search.provider_name}")
    print(f"Sources in State: {len(state.sources)}")
    print(f"Evidence in State: {len(state.evidence_pool)}")
    if state.final_report:
        print(f"Report Title: {state.final_report.title}")


if __name__ == "__main__":
    asyncio.run(main())
