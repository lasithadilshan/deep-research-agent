from pathlib import Path

import pytest

from deep_research.agents.extractor import ExtractedEvidenceBatch, RawExtractedClaim
from deep_research.agents.planner import GeneratedResearchPlan, GeneratedSubQuestion
from deep_research.agents.synthesizer import DraftReportPayload, DraftSection
from deep_research.core.exceptions import ResearchCancelledError
from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models.evidence import ConfidenceLevel
from deep_research.models.plan import ResearchMode, ResearchPlan, SubQuestion
from deep_research.models.search import SearchResponse, SearchResult
from deep_research.models.state import ResearchStatus
from deep_research.providers.llm.mock import MockLLMProvider
from deep_research.providers.search.mock import MockSearchProvider
from deep_research.storage.cache import ResearchCache
from deep_research.storage.session_store import SessionStore


@pytest.mark.asyncio
async def test_orchestrator_plan_approver_modifies_plan(tmp_path: Path) -> None:
    mock_llm = MockLLMProvider()
    mock_search = MockSearchProvider()
    session_store = SessionStore(sessions_dir=tmp_path / "sessions")

    # Queue plan response
    mock_llm.queue_structured_response(
        GeneratedResearchPlan(
            primary_objective="Test Energy Storage",
            hypotheses=["Hypothesis A"],
            sub_questions=[
                GeneratedSubQuestion(
                    question_id="SQ-1",
                    question="Question 1?",
                    rationale="Rationale 1",
                    target_queries=["query 1"],
                )
            ],
            initial_search_queries=["query 1"],
        )
    )

    # Queue search hit
    source_content = (
        "Solid state batteries have demonstrated high gravimetric energy density exceeding "
        "500 Wh/kg in prototype pouch cells under controlled laboratory testing environments."
    )
    mock_search.queue_response(
        SearchResponse(
            query="query 1",
            results=[
                SearchResult(
                    title="Battery Lab",
                    url="https://batterylab.org/report",
                    snippet="Solid state achieves 500 Wh/kg with safety.",
                    direct_markdown=source_content,
                )
            ],
            provider_name="mock",
            execution_time_ms=10.0,
        )
    )

    # Queue extractor hit
    mock_llm.queue_structured_response(
        ExtractedEvidenceBatch(
            claims=[
                RawExtractedClaim(
                    claim="Solid state achieves 500 Wh/kg.",
                    exact_quote="Solid state batteries have demonstrated high gravimetric energy density exceeding 500 Wh/kg",
                    sub_question_id="SQ-1",
                    confidence=ConfidenceLevel.HIGH,
                )
            ]
        )
    )

    # Queue synthesis draft
    mock_llm.queue_structured_response(
        DraftReportPayload(
            title="Battery Synthesis",
            executive_summary="Solid state batteries reach 500 Wh/kg [EV-001].",
            sections=[
                DraftSection(
                    title="Findings",
                    content="Energy density reached 500 Wh/kg [EV-001].",
                )
            ],
            research_methodology="Mock methodology",
            known_limitations=["Lab testing only"],
        )
    )

    cache = ResearchCache(db_path=tmp_path / "cache.db")
    orchestrator = ResearchOrchestrator(
        llm=mock_llm,
        search_provider=mock_search,
        session_store=session_store,
        cache=cache,
    )

    def modifier_approver(plan: ResearchPlan) -> ResearchPlan:
        # Add an additional sub-question
        plan.sub_questions.append(
            SubQuestion(
                question_id="SQ-2",
                question="What are the cycle life limits?",
                rationale="Safety check",
                target_queries=["battery cycle life 1000 cycles"],
            )
        )
        return plan

    state = await orchestrator.execute_research(
        query="Test Energy Storage",
        mode=ResearchMode.QUICK,
        plan_approver=modifier_approver,
    )

    assert state.status == ResearchStatus.COMPLETED
    assert state.plan is not None
    assert len(state.plan.sub_questions) == 2
    assert state.plan.sub_questions[1].question_id == "SQ-2"
    assert any("Plan modified and approved by human reviewer" in log for log in state.audit_log)


@pytest.mark.asyncio
async def test_orchestrator_plan_approver_cancellation(tmp_path: Path) -> None:
    mock_llm = MockLLMProvider()
    mock_search = MockSearchProvider()
    session_store = SessionStore(sessions_dir=tmp_path / "sessions")

    mock_llm.queue_structured_response(
        GeneratedResearchPlan(
            primary_objective="Topic to Cancel",
            hypotheses=["H1"],
            sub_questions=[
                GeneratedSubQuestion(
                    question_id="SQ-1",
                    question="Q1?",
                    rationale="R1",
                    target_queries=["q1"],
                )
            ],
            initial_search_queries=["q1"],
        )
    )

    orchestrator = ResearchOrchestrator(
        llm=mock_llm,
        search_provider=mock_search,
        session_store=session_store,
    )

    def cancel_approver(plan: ResearchPlan) -> ResearchPlan | None:
        return None

    with pytest.raises(ResearchCancelledError):
        await orchestrator.execute_research(
            query="Topic to Cancel",
            mode=ResearchMode.QUICK,
            plan_approver=cancel_approver,
        )

    # Verify state was saved with CANCELLED status
    saved_sessions = session_store.list_sessions()
    assert len(saved_sessions) == 1
    assert saved_sessions[0].status == ResearchStatus.CANCELLED
