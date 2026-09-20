"""Integration test verifying the multi-turn deep research iteration loop."""

import pytest

from deep_research.agents.analyst import GapAnalysisOutput
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
async def test_multi_turn_deep_iteration_loop() -> None:
    mock_llm = MockLLMProvider()
    mock_search = MockSearchProvider()

    # 1. Planner response (2 sub-questions)
    plan = GeneratedResearchPlan(
        primary_objective="Analyze Solid-State Battery Commercial Readiness",
        hypotheses=["Automotive solid-state batteries will reach volume production before 2030."],
        sub_questions=[
            GeneratedSubQuestion(
                question_id="SQ-1",
                question="What are the current energy densities achieved in solid-state prototypes?",
                rationale="Assess technological density milestones",
                target_queries=["solid-state battery prototype energy density Wh/kg"],
            ),
            GeneratedSubQuestion(
                question_id="SQ-2",
                question="What are the primary manufacturing yield bottlenecks?",
                rationale="Assess industrial scaling challenges",
                target_queries=[],
            ),
        ],
        initial_search_queries=["solid-state battery prototype energy density Wh/kg"],
    )
    mock_llm.queue_structured_response(plan)

    # 2. Iteration 1 Search Response
    hit_iter1 = SearchResult(
        title="Solid Power 2025 Cell Data",
        url="https://solidpowerbattery.example.com/specs",
        snippet="Prototypes achieve 390 Wh/kg in 20Ah pouch cells.",
        direct_markdown=(
            "Solid Power demonstrates 390 Wh/kg specific energy density in automotive pouch format prototypes "
            "tested under standard laboratory conditions, surpassing commercial lithium-ion benchmarks significantly."
        ),
    )
    mock_search.queue_response(
        SearchResponse(
            query="solid-state battery prototype energy density Wh/kg",
            results=[hit_iter1],
            provider_name="mock",
        )
    )

    # 3. Iteration 1 Extractor Response
    mock_llm.queue_structured_response(
        ExtractedEvidenceBatch(
            claims=[
                RawExtractedClaim(
                    claim="Automotive solid-state pouch prototypes have demonstrated 390 Wh/kg.",
                    exact_quote="Solid Power demonstrates 390 Wh/kg specific energy density in automotive pouch format",
                    confidence=ConfidenceLevel.VERIFIED,
                )
            ]
        )
    )

    # 4. Iteration 1 Analyst Response: Detects SQ-2 is unanswered, suggests targeted query
    mock_llm.queue_structured_response(
        GapAnalysisOutput(
            unresolved_questions=["What are the primary manufacturing yield bottlenecks?"],
            conflicts=[],
            suggested_follow_up_queries=[
                "solid state battery electrolyte separator cracking yield"
            ],
        )
    )

    # 5. Iteration 2 Search Response (Follow-up Query)
    hit_iter2 = SearchResult(
        title="Industrial Scaling of Solid Electrolytes",
        url="https://battery-manufacturing.example.com/yields",
        snippet="Ceramic separator brittle fracturing causes 30% yield loss in roll-to-roll pressing.",
        direct_markdown=(
            "Micro-cracking in brittle ceramic oxide separators during high-speed calendering causes substantial yield drops, "
            "making web handling and continuous roll-to-roll processing a primary industrial engineering bottleneck."
        ),
    )
    mock_search.queue_response(
        SearchResponse(
            query="solid state battery electrolyte separator cracking yield",
            results=[hit_iter2],
            provider_name="mock",
        )
    )

    # 6. Iteration 2 Extractor Response
    mock_llm.queue_structured_response(
        ExtractedEvidenceBatch(
            claims=[
                RawExtractedClaim(
                    claim="Ceramic separator micro-cracking during calendering is the primary yield bottleneck.",
                    exact_quote="Micro-cracking in brittle ceramic oxide separators during high-speed calendering causes substantial yield drops",
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
    )

    # 7. Iteration 2 Analyst Response: Both sub-questions answered, no follow-ups needed
    mock_llm.queue_structured_response(
        GapAnalysisOutput(
            unresolved_questions=[],
            conflicts=[],
            suggested_follow_up_queries=[],
        )
    )

    # 8. Synthesizer Response
    mock_llm.queue_structured_response(
        DraftReportPayload(
            title="Commercial Viability of Solid-State Batteries",
            executive_summary="Solid-state cells have reached 390 Wh/kg [EV-001], but ceramic separator fracturing [EV-002] hinders high-throughput production.",
            sections=[
                DraftSection(
                    title="Energy Density Benchmarks",
                    content="Automotive pouch prototypes have demonstrated 390 Wh/kg [EV-001].",
                ),
                DraftSection(
                    title="Manufacturing Scaling Bottlenecks",
                    content="Separator micro-cracking during high-speed calendering creates yield bottlenecks [EV-002].",
                ),
            ],
            known_limitations=[
                "Long-term cycling retention data under fast charging remains proprietary."
            ],
        )
    )

    # 9. Run Orchestrator with STANDARD mode (max_iterations = 2)
    orchestrator = ResearchOrchestrator(
        llm=mock_llm,
        search_provider=mock_search,
    )

    state = await orchestrator.execute_research(
        query="Analyze Solid-State Battery Commercial Readiness",
        mode=ResearchMode.STANDARD,
        max_budget_usd=1.00,
    )

    # 10. Assertions
    assert state.status == ResearchStatus.COMPLETED
    assert state.current_iteration == 2
    assert len(state.sources) == 2
    assert len(state.evidence_pool) == 2
    assert len(state.findings) == 2
    assert state.final_report is not None

    # Verify both citations were audited and converted from [EV-001], [EV-002] to [1], [2]
    assert "[1]" in state.final_report.executive_summary
    assert "[2]" in state.final_report.executive_summary
    assert "[EV-" not in state.final_report.to_markdown()

    # Verify bibliography has both entries
    assert len(state.final_report.bibliography) == 2
    urls = [b.url for b in state.final_report.bibliography]
    assert any("solidpowerbattery" in u for u in urls)
    assert any("battery-manufacturing" in u for u in urls)
