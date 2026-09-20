"""Unit tests for AnalystAgent evaluating evidence density, gaps, and contradictions."""

import pytest

from deep_research.agents.analyst import (
    AnalystAgent,
    GapAnalysisOutput,
    IdentifiedConflict,
)
from deep_research.models.evidence import ConfidenceLevel, Evidence
from deep_research.models.plan import ResearchPlan, SubQuestion
from deep_research.models.source import Source
from deep_research.models.state import ResearchState
from deep_research.providers.llm.mock import MockLLMProvider


@pytest.mark.asyncio
async def test_analyst_agent_empty_evidence() -> None:
    mock_llm = MockLLMProvider()
    analyst = AnalystAgent(llm=mock_llm)

    state = ResearchState(initial_query="What is quantum teleportation?")
    result = await analyst.execute(state)

    assert result.status == "completed"
    assert result.items_produced == 0
    assert len(mock_llm.calls) == 0


@pytest.mark.asyncio
async def test_analyst_agent_evaluates_density_and_detects_conflicts() -> None:
    mock_llm = MockLLMProvider()
    analyst = AnalystAgent(llm=mock_llm)

    state = ResearchState(initial_query="Assess solid-state battery commercialization timeline.")

    # Plan with 2 sub-questions
    sq1 = SubQuestion(
        question_id="SQ-1",
        question="Which automotive OEMs have announced commercial solid-state battery roadmaps?",
        target_queries=["solid state battery OEM roadmaps"],
    )
    sq2 = SubQuestion(
        question_id="SQ-2",
        question="What is the projected mass production year?",
        target_queries=["solid state battery mass production year"],
    )
    state.plan = ResearchPlan(
        primary_objective="Assess timeline",
        sub_questions=[sq1, sq2],
    )

    # Ingest sources
    src1 = Source.create(
        url="https://toyota-tech.example.com/battery",
        title="Toyota Roadmap",
        snippet="Toyota plans commercial solid-state rollout by 2027-2028.",
        cleaned_markdown="Toyota plans commercial solid-state rollout by 2027-2028.",
    )
    src2 = Source.create(
        url="https://market-analyst.example.com/ev-trends",
        title="EV Market Outlook",
        snippet="Analysts forecast volume production delayed until 2032.",
        cleaned_markdown="Analysts forecast volume production delayed until 2032.",
    )
    state.add_source(src1)
    state.add_source(src2)

    # Ingest evidence: SQ-1 has high confidence evidence; SQ-2 has conflicting dates
    ev1 = Evidence(
        evidence_id="EV-001",
        source_id=src1.source_id,
        source_url=src1.url,
        sub_question_id=sq1.question_id,
        claim="Toyota targets 2027-2028 for solid-state commercialization.",
        exact_quote="Toyota plans commercial solid-state rollout by 2027-2028.",
        confidence=ConfidenceLevel.VERIFIED,
    )
    ev2 = Evidence(
        evidence_id="EV-002",
        source_id=src2.source_id,
        source_url=src2.url,
        sub_question_id=sq2.question_id,
        claim="Industry analysts estimate mass production delayed to 2032.",
        exact_quote="Analysts forecast volume production delayed until 2032.",
        confidence=ConfidenceLevel.HIGH,
    )
    state.add_evidence(ev1)
    state.add_evidence(ev2)

    sq1.evidence_ids.append(ev1.evidence_id)
    sq2.evidence_ids.append(ev2.evidence_id)

    # Queue structured analysis output
    analysis_output = GapAnalysisOutput(
        unresolved_questions=["What is the projected mass production year?"],
        conflicts=[
            IdentifiedConflict(
                topic="Production Timeline",
                conflicting_evidence_ids=["EV-001", "EV-002"],
                explanation="Toyota projects 2027-2028 rollout while market analysts forecast delay to 2032.",
                resolution_query="solid state battery pilot line production capacity 2027",
            )
        ],
        suggested_follow_up_queries=["solid state battery pilot line production capacity 2027"],
    )
    mock_llm.queue_structured_response(analysis_output)

    result = await analyst.execute(state)

    assert result.status == "completed"
    assert analyst.last_analysis is not None
    assert len(analyst.last_analysis.conflicts) == 1
    assert len(state.identified_conflicts) == 1
    assert "Production Timeline" in state.identified_conflicts[0]

    # Findings compiled
    assert len(state.findings) == 2
    assert state.findings[0].topic == sq1.question
    assert state.findings[0].confidence == ConfidenceLevel.HIGH


@pytest.mark.asyncio
async def test_analyst_agent_fallback_on_llm_failure() -> None:
    mock_llm = MockLLMProvider()
    analyst = AnalystAgent(llm=mock_llm)

    state = ResearchState(initial_query="Investigate room temperature superconductors.")
    sq = SubQuestion(
        question_id="SQ-1",
        question="Are there validated room temperature ambient pressure superconductors?",
    )
    state.plan = ResearchPlan(primary_objective="Superconductors", sub_questions=[sq])

    src = Source.create(
        url="https://nature.example.com/paper",
        title="Superconductor Study",
        snippet="LK-99 was debunked as a ferromagnet, not a superconductor.",
    )
    state.add_source(src)
    ev = Evidence(
        evidence_id="EV-001",
        source_id=src.source_id,
        source_url=src.url,
        sub_question_id=sq.question_id,
        claim="LK-99 exhibited ferromagnetism rather than superconductivity.",
        exact_quote="LK-99 was debunked as a ferromagnet, not a superconductor.",
        confidence=ConfidenceLevel.HIGH,
    )
    state.add_evidence(ev)
    sq.evidence_ids.append(ev.evidence_id)

    # Queue an error in LLM
    mock_llm.queue_error(RuntimeError("API quota exceeded"))

    result = await analyst.execute(state)

    assert result.status == "completed_fallback"
    assert analyst.last_analysis is not None
    assert len(analyst.last_analysis.suggested_follow_up_queries) >= 0
    assert any("Analyst cross-examination failed" in log for log in state.audit_log)
