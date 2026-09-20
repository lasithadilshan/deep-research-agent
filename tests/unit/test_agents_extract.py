"""Unit tests for EvaluatorAgent and ExtractorAgent."""

import pytest

from deep_research.agents.evaluator import EvaluatorAgent
from deep_research.agents.extractor import (
    ExtractedEvidenceBatch,
    ExtractorAgent,
    RawExtractedClaim,
)
from deep_research.models import (
    BudgetTracker,
    ConfidenceLevel,
    ResearchMode,
    ResearchPlan,
    ResearchState,
    Source,
    SourceType,
    SubQuestion,
)
from deep_research.providers.llm.mock import MockLLMProvider


class TestEvaluatorAgent:
    @pytest.mark.asyncio
    async def test_evaluator_retains_valid_and_enriches_academic(self) -> None:
        state = ResearchState(
            initial_query="Superconducting qubits",
            mode=ResearchMode.STANDARD,
        )
        good_source = Source.create(
            url="https://arxiv.org/abs/2401.00001",
            title="Superconducting Qubit Advances",
            cleaned_markdown="This is a long and comprehensive academic paper regarding superconducting qubit coherence times. "
            * 3,
        )
        state.add_source(good_source)

        evaluator = EvaluatorAgent()
        result = await evaluator.execute(state)

        assert result.status == "completed"
        assert len(state.sources) == 1
        assert state.sources[good_source.source_id].source_type == SourceType.ACADEMIC_PAPER
        assert state.sources[good_source.source_id].credibility.is_tld_verified is True

    @pytest.mark.asyncio
    async def test_evaluator_rejects_short_content(self) -> None:
        state = ResearchState(initial_query="Test query")
        short_source = Source.create(
            url="https://example.com/short",
            title="Too short",
            cleaned_markdown="Very short text.",
        )
        state.add_source(short_source)

        evaluator = EvaluatorAgent()
        result = await evaluator.execute(state)

        assert len(state.sources) == 0
        assert result.items_produced == 0
        assert any("below threshold" in log for log in state.audit_log)

    @pytest.mark.asyncio
    async def test_evaluator_rejects_blocked_anti_bot_pages(self) -> None:
        state = ResearchState(initial_query="Test query")
        blocked_source = Source.create(
            url="https://protected.com/article",
            title="Blocked",
            cleaned_markdown="Access Denied: You do not have permission to access this server on this URL. "
            * 5,
        )
        state.add_source(blocked_source)

        evaluator = EvaluatorAgent()
        await evaluator.execute(state)

        assert len(state.sources) == 0
        assert any("Anti-bot/error pattern detected" in log for log in state.audit_log)


class TestExtractorAgent:
    @pytest.mark.asyncio
    async def test_extractor_extracts_grounded_claims(self) -> None:
        mock_llm = MockLLMProvider()
        source_text = (
            "The physical error rate of the superconducting processor was measured at 0.12%, "
            "which falls well below the fault-tolerant threshold."
        )
        source = Source.create(
            url="https://nature.com/articles/phys-error-1",
            title="Physical Error Rates",
            cleaned_markdown=source_text,
        )

        state = ResearchState(initial_query="Error rates")
        state.add_source(source)
        state.plan = ResearchPlan(
            primary_objective="Measure error rates",
            sub_questions=[SubQuestion(question_id="SQ-1", question="What are error rates?")],
            initial_search_queries=["error rates"],
        )

        # Queue valid claim with verbatim quote from text
        valid_batch = ExtractedEvidenceBatch(
            claims=[
                RawExtractedClaim(
                    claim="Processor physical error rate is 0.12%",
                    exact_quote="physical error rate of the superconducting processor was measured at 0.12%",
                    confidence=ConfidenceLevel.VERIFIED,
                )
            ]
        )
        mock_llm.queue_structured_response(valid_batch)

        extractor = ExtractorAgent(llm=mock_llm)
        result = await extractor.execute(state)

        assert result.status == "completed"
        assert len(state.evidence_pool) == 1
        ev = next(iter(state.evidence_pool.values()))
        assert ev.claim == "Processor physical error rate is 0.12%"
        assert ev.confidence == ConfidenceLevel.VERIFIED
        assert ev.sub_question_id == "SQ-1"
        assert state.budget.current_cost_usd > 0.0

    @pytest.mark.asyncio
    async def test_extractor_rejects_hallucinated_quotes(self) -> None:
        mock_llm = MockLLMProvider()
        source_text = (
            "Real paper about quantum physics without any mention of magical teleportation. "
            "It discusses standard laboratory measurements of spin dynamics."
        )
        source = Source.create(
            url="https://nature.com/articles/real-doc",
            title="Quantum Physics",
            cleaned_markdown=source_text,
        )

        state = ResearchState(initial_query="Teleportation")
        state.add_source(source)

        hallucinated_batch = ExtractedEvidenceBatch(
            claims=[
                RawExtractedClaim(
                    claim="Humans were successfully teleported to Mars.",
                    exact_quote="We successfully teleported three humans directly to Mars.",
                    confidence=ConfidenceLevel.LOW,
                )
            ]
        )
        mock_llm.queue_structured_response(hallucinated_batch)

        extractor = ExtractorAgent(llm=mock_llm)
        result = await extractor.execute(state)

        # The hallucinated claim should be discarded because the quote is not in source_text
        assert len(state.evidence_pool) == 0
        assert result.items_produced == 0
        assert any("rejected ungrounded claim" in log for log in state.audit_log)

    @pytest.mark.asyncio
    async def test_extractor_halts_when_budget_exceeded(self) -> None:
        mock_llm = MockLLMProvider()
        source = Source.create(
            url="https://example.com/doc",
            title="Doc",
            cleaned_markdown="Some valid long content text describing algorithms." * 10,
        )
        state = ResearchState(
            initial_query="Test",
            budget=BudgetTracker(max_budget_usd=0.05, current_cost_usd=0.06),
        )
        state.add_source(source)

        extractor = ExtractorAgent(llm=mock_llm)
        await extractor.execute(state)

        assert any("budget ceiling exceeded" in log for log in state.audit_log)
        assert len(state.evidence_pool) == 0
