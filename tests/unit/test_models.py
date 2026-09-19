"""Unit tests for core Pydantic models."""

import pytest
from pydantic import ValidationError

from deep_research.models import (
    BudgetTracker,
    Citation,
    Evidence,
    ResearchMode,
    ResearchPlan,
    ResearchReport,
    ResearchState,
    ResearchStatus,
    SearchQuery,
    SearchResponse,
    SearchResult,
    Section,
    Source,
    StepResult,
    SubQuestion,
    TokenUsage,
    canonicalize_url,
    generate_source_id,
)


class TestSourceAndCredibility:
    def test_canonicalize_url_strips_tracking(self) -> None:
        raw = "https://WWW.Nature.Com/articles/123/?utm_source=twitter&utm_medium=social&ref=feed#anchor"
        expected = "https://www.nature.com/articles/123"
        assert canonicalize_url(raw) == expected

    def test_generate_source_id_deterministic(self) -> None:
        url1 = "https://arxiv.org/abs/2401.00001"
        url2 = "https://arxiv.org/abs/2401.00001?utm_campaign=share"
        id1 = generate_source_id(canonicalize_url(url1))
        id2 = generate_source_id(canonicalize_url(url2))
        assert id1 == id2
        assert id1.startswith("src-")

    def test_source_factory_detects_academic_domain(self) -> None:
        source = Source.create(
            url="https://arxiv.org/abs/2401.12345",
            title="Quantum Memory",
            cleaned_markdown="Superconducting qubit state storage.",
        )
        assert source.credibility.is_tld_verified is True
        assert source.credibility.domain == "arxiv.org"
        assert source.credibility.is_https is True
        assert source.credibility.content_length_chars == len(
            "Superconducting qubit state storage."
        )

    def test_source_factory_handles_commercial_domain(self) -> None:
        source = Source.create(
            url="http://techblog.example.com/post/",
            title="Tech Blog",
        )
        assert source.credibility.is_tld_verified is False
        assert source.credibility.is_https is False


class TestEvidenceAndGrounding:
    def test_evidence_quote_verification_success(
        self, sample_evidence: Evidence, sample_source: Source
    ) -> None:
        assert sample_evidence.verify_quote_grounding(sample_source.cleaned_markdown) is True

    def test_evidence_quote_verification_handles_whitespace(self, sample_source: Source) -> None:
        evidence = Evidence(
            evidence_id="EV-002",
            source_id=sample_source.source_id,
            source_url=sample_source.canonical_url,
            claim="Physical error rates test",
            exact_quote="physical error rates\n  below 0.5% achieve exponential suppression",
            sub_question_id="SQ-1",
        )
        assert evidence.verify_quote_grounding(sample_source.cleaned_markdown) is True

    def test_evidence_quote_verification_detects_hallucination(self, sample_source: Source) -> None:
        evidence = Evidence(
            evidence_id="EV-003",
            source_id=sample_source.source_id,
            source_url=sample_source.canonical_url,
            claim="Fake claim",
            exact_quote="this sentence definitely does not exist in the paper",
            sub_question_id="SQ-1",
        )
        assert evidence.verify_quote_grounding(sample_source.cleaned_markdown) is False

    def test_evidence_quote_verification_empty_inputs(self) -> None:
        evidence_empty = Evidence(
            evidence_id="EV-004",
            source_id="src-123",
            source_url="https://example.com",
            claim="Test claim",
            exact_quote="",
            sub_question_id="SQ-1",
        )
        assert evidence_empty.verify_quote_grounding("Some content") is False
        evidence_valid = Evidence(
            evidence_id="EV-005",
            source_id="src-123",
            source_url="https://example.com",
            claim="Test claim",
            exact_quote="valid quote",
            sub_question_id="SQ-1",
        )
        assert evidence_valid.verify_quote_grounding("") is False


class TestBudgetAndCost:
    def test_token_usage_total_tokens(self) -> None:
        usage = TokenUsage(prompt_tokens=150, completion_tokens=50, cost_usd=0.001)
        assert usage.total_tokens == 200

    def test_budget_tracker_limits_and_recording(self) -> None:
        tracker = BudgetTracker(max_budget_usd=0.10)
        assert tracker.is_exceeded is False
        assert tracker.remaining_budget_usd == 0.10

        tracker.record_llm_call(prompt_tokens=1000, completion_tokens=500, cost_usd=0.04)
        assert tracker.prompt_tokens == 1000
        assert tracker.completion_tokens == 500
        assert tracker.current_cost_usd == 0.04
        assert tracker.is_exceeded is False

        tracker.record_search_call(cost_usd=0.07)
        assert tracker.search_api_calls == 1
        assert tracker.current_cost_usd == 0.11
        assert tracker.is_exceeded is True
        assert tracker.remaining_budget_usd == 0.0

    def test_budget_tracker_negative_budget_raises(self) -> None:
        with pytest.raises(ValidationError):
            BudgetTracker(max_budget_usd=-1.0)


class TestReportAndCitations:
    def test_citation_reference_formatting(self) -> None:
        citation = Citation(
            numeric_index=1,
            source_id="src-1234567890",
            url="https://nature.com/articles/123",
            title="Quantum Fault Tolerance",
            author="Fowler et al.",
            published_date="2024-05-12",
            accessed_date="2026-09-19",
            verbatim_quote_anchor="threshold rate of 1%",
        )
        formatted = citation.format_reference_entry()
        assert '[1] Fowler et al., "Quantum Fault Tolerance" (2024-05-12).' in formatted
        assert "Retrieved 2026-09-19 from https://nature.com/articles/123" in formatted

    def test_report_to_markdown(self) -> None:
        citation = Citation(
            numeric_index=1,
            source_id="src-1",
            url="https://example.com/doc",
            title="Example Study",
            accessed_date="2026-09-19",
            verbatim_quote_anchor="Key discovery",
        )
        section = Section(
            title="Introduction",
            content="Recent advances show significant progress [1].",
            cited_numbers=[1],
        )
        report = ResearchReport(
            title="State of Quantum Error Correction",
            executive_summary="Quantum error correction is progressing rapidly.",
            sections=[section],
            bibliography=[citation],
            research_methodology="Systematic literature review across arXiv and peer-reviewed journals.",
            known_limitations=["Hardware availability is restricted."],
            total_sources_consulted=5,
            total_evidence_pieces=12,
        )

        md = report.to_markdown()
        assert "# State of Quantum Error Correction" in md
        assert "## Executive Summary" in md
        assert "## Introduction" in md
        assert "Recent advances show significant progress [1]." in md
        assert "## Methodology Notes" in md
        assert "Systematic literature review" in md
        assert "## References" in md
        assert '[1] "Example Study".' in md
        assert "- Hardware availability is restricted." in md


class TestResearchPlanAndSearch:
    def test_search_query_and_response(self) -> None:
        query = SearchQuery(query_text="surface code error threshold", priority=1)
        res = SearchResult(
            title="Surface Code Thresholds",
            url="https://arxiv.org/abs/2101.12345",
            snippet="Overview of physical thresholds.",
        )
        response = SearchResponse(
            query=query.query_text,
            results=[res],
            provider_name="Tavily",
            execution_time_ms=180.5,
        )
        assert len(response.results) == 1
        assert response.results[0].title == "Surface Code Thresholds"

    def test_research_plan_initialization(self) -> None:
        sub_q = SubQuestion(
            question_id="SQ-1",
            question="What are typical physical error rates?",
            target_queries=["physical error rate quantum computing"],
        )
        plan = ResearchPlan(
            primary_objective="Evaluate surface code viability",
            sub_questions=[sub_q],
            initial_search_queries=["surface code threshold 2025"],
            planned_mode=ResearchMode.STANDARD,
        )
        assert len(plan.sub_questions) == 1
        assert plan.sub_questions[0].is_answered is False


class TestResearchState:
    def test_state_transitions_and_audit(self, sample_state: ResearchState) -> None:
        initial_status: ResearchStatus = sample_state.status
        assert initial_status == ResearchStatus.INITIALIZED
        sample_state.transition_to(ResearchStatus.PLANNING, "Starting plan generation")
        updated_status: ResearchStatus = sample_state.status
        assert updated_status == ResearchStatus.PLANNING
        assert len(sample_state.audit_log) == 1
        assert (
            "State transition: initialized -> planning (Starting plan generation)"
            in sample_state.audit_log[0]
        )

    def test_add_source_deduplication(
        self, sample_state: ResearchState, sample_source: Source
    ) -> None:
        first_add = sample_state.add_source(sample_source)
        second_add = sample_state.add_source(sample_source)
        assert first_add is True
        assert second_add is False
        assert len(sample_state.sources) == 1

    def test_add_evidence_deduplication(
        self, sample_state: ResearchState, sample_evidence: Evidence
    ) -> None:
        first_add = sample_state.add_evidence(sample_evidence)
        second_add = sample_state.add_evidence(sample_evidence)
        assert first_add is True
        assert second_add is False
        assert len(sample_state.evidence_pool) == 1

    def test_step_result_recording(self, sample_state: ResearchState) -> None:
        step = StepResult(
            agent_name="ResearcherAgent",
            status="success",
            summary="Retrieved 5 sources across 3 queries",
            duration_ms=450.0,
            items_produced=5,
        )
        sample_state.record_step(step)
        assert len(sample_state.step_history) == 1
        assert sample_state.step_history[0].agent_name == "ResearcherAgent"

    def test_record_audit(self, sample_state: ResearchState) -> None:
        sample_state.record_audit("Manual verification note")
        assert any("Manual verification note" in entry for entry in sample_state.audit_log)
