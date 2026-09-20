"""Integration tests for the complete linear research loop."""

import pytest

from deep_research.agents.extractor import ExtractedEvidenceBatch, RawExtractedClaim
from deep_research.agents.planner import GeneratedResearchPlan, GeneratedSubQuestion
from deep_research.agents.synthesizer import DraftReportPayload, DraftSection
from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models import (
    ConfidenceLevel,
    ResearchMode,
    ResearchStatus,
    SearchResponse,
    SearchResult,
)
from deep_research.providers.llm.mock import MockLLMProvider
from deep_research.providers.search.mock import MockSearchProvider


@pytest.mark.asyncio
async def test_full_linear_research_pipeline() -> None:
    # 1. Setup Mock LLM and Search
    mock_llm = MockLLMProvider()
    mock_search = MockSearchProvider()

    # 2. Plan generation mock
    plan_response = GeneratedResearchPlan(
        primary_objective="Evaluate Perovskite Solar Cell Efficiency",
        hypotheses=["Tandem silicon-perovskite cells exceed 33% power conversion efficiency."],
        sub_questions=[
            GeneratedSubQuestion(
                question_id="SQ-1",
                question="What is the certified world record efficiency for perovskite-silicon tandems?",
                rationale="Quantify latest certified laboratory benchmarks",
                target_queries=["certified perovskite tandem solar cell efficiency record 2025"],
            )
        ],
        initial_search_queries=["perovskite tandem efficiency 2025"],
    )
    mock_llm.queue_structured_response(plan_response)

    # 3. Search hits mock (delivering pre-scraped markdown content)
    source_content = (
        "National Renewable Energy Laboratory certified a monolithic perovskite-silicon tandem "
        "solar cell achieving a power conversion efficiency of 33.9% under standard testing conditions."
    )
    search_hit = SearchResult(
        title="NREL Certified Tandem Solar Cell Record",
        url="https://www.nrel.gov/news/press/2025/perovskite-record.html",
        snippet="NREL confirms 33.9% power conversion efficiency milestone.",
        direct_markdown=source_content,
        raw_score=0.99,
        published_date="2025-03-10",
    )
    mock_search.queue_response(
        SearchResponse(
            query="perovskite tandem efficiency 2025",
            results=[search_hit],
            provider_name="mock",
            execution_time_ms=50.0,
        )
    )

    # 4. Extractor mock (delivering claim with verbatim quote from source)
    mock_llm.queue_structured_response(
        ExtractedEvidenceBatch(
            claims=[
                RawExtractedClaim(
                    claim="Perovskite-silicon tandem cells achieved 33.9% certified efficiency.",
                    exact_quote="perovskite-silicon tandem solar cell achieving a power conversion efficiency of 33.9%",
                    confidence=ConfidenceLevel.VERIFIED,
                )
            ]
        )
    )

    # 5. Synthesizer mock (generating report citing [EV-001])
    # Note: the orchestrator synthesizes the draft and the auditor renumbers it
    mock_llm.queue_structured_response(
        DraftReportPayload(
            title="State of Perovskite Photovoltaics 2026",
            executive_summary="Certified perovskite tandem cells reached 33.9% efficiency [EV-001].",
            sections=[
                DraftSection(
                    title="Certified Efficiency Benchmarks",
                    content="NREL testing confirmed record performance [EV-001] for monolithic architectures.",
                )
            ],
            known_limitations=[
                "Long-term outdoor operational stability under moisture remains under trial."
            ],
        )
    )

    # 6. Execute End-to-End Pipeline
    orchestrator = ResearchOrchestrator(
        llm=mock_llm,
        search_provider=mock_search,
    )

    state = await orchestrator.execute_research(
        query="What is the certified efficiency of perovskite solar cells?",
        mode=ResearchMode.QUICK,
        max_budget_usd=1.00,
    )

    # 7. Verification of Final State
    assert state.status == ResearchStatus.COMPLETED
    assert state.final_report is not None
    assert state.final_report.title == "State of Perovskite Photovoltaics 2026"

    # Citation renumbering checks: [EV-xxx] -> [1]
    assert "[1]" in state.final_report.executive_summary
    assert "[1]" in state.final_report.sections[0].content
    assert "[EV-" not in state.final_report.sections[0].content

    # Bibliography checks
    assert len(state.final_report.bibliography) == 1
    citation = state.final_report.bibliography[0]
    assert citation.numeric_index == 1
    assert "nrel.gov" in citation.url
    assert "33.9%" in citation.verbatim_quote_anchor

    # Telemetry and budget checks
    assert len(state.sources) == 1
    assert len(state.evidence_pool) == 1
    assert state.budget.prompt_tokens > 0
    assert state.budget.completion_tokens > 0
    assert state.budget.current_cost_usd > 0.0

    # Markdown export check
    report_markdown = state.final_report.to_markdown()
    assert "# State of Perovskite Photovoltaics 2026" in report_markdown
    assert "## Executive Summary" in report_markdown
    assert "## References" in report_markdown
    assert "[1]" in report_markdown
