"""Minimal programmatic example executing a research inquiry using the ResearchOrchestrator."""

import asyncio

from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models.plan import ResearchMode


async def main() -> None:
    # Uses GEMINI_API_KEY and TAVILY_API_KEY from environment, or falls back to Mock provider
    orchestrator = ResearchOrchestrator()

    query = "Certified power conversion efficiency records of perovskite-silicon tandem solar cells"
    print(f"Starting research for: '{query}'\n")

    state = await orchestrator.execute_research(
        query=query,
        mode=ResearchMode.QUICK,
        status_callback=lambda msg: print(f"[*] {msg}"),
    )

    print("\n" + "=" * 60)
    print(f"Status: {state.status.value}")
    print(f"Sources Gathered: {len(state.sources)}")
    print(f"Evidence Claims Extracted: {len(state.evidence_pool)}")
    print(f"Total Cost: ${state.budget.current_cost_usd:.6f}")
    print("=" * 60 + "\n")

    if state.final_report:
        print(state.final_report.to_markdown())


if __name__ == "__main__":
    asyncio.run(main())
