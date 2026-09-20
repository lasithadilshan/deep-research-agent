"""Unit tests for SynthesizerAgent and CitationAuditorAgent."""

import pytest

from deep_research.agents.auditor import CitationAuditorAgent
from deep_research.agents.synthesizer import (
    DraftReportPayload,
    DraftSection,
    SynthesizerAgent,
)
from deep_research.models import (
    ConfidenceLevel,
    Evidence,
    ResearchState,
    ResearchStatus,
    Source,
)
from deep_research.providers.llm.mock import MockLLMProvider


class TestSynthesizerAndAuditor:
    @pytest.mark.asyncio
    async def test_synthesizer_generates_draft_with_tokens(self) -> None:
        mock_llm = MockLLMProvider()
        draft = DraftReportPayload(
            title="State of Quantum Error Correction 2026",
            executive_summary="Surface codes exhibit error suppression below 0.12% [EV-001].",
            sections=[
                DraftSection(
                    title="Empirical Results",
                    content="Recent superconducting benchmarks confirm threshold crossings [EV-001].",
                )
            ],
            known_limitations=["Cryogenic scale remains an engineering hurdle."],
        )
        mock_llm.queue_structured_response(draft)

        state = ResearchState(initial_query="Quantum Error Correction")
        state.evidence_pool["EV-001"] = Evidence(
            evidence_id="EV-001",
            source_id="src-1",
            source_url="https://arxiv.org/abs/2401.00001",
            claim="Threshold crossing measured below 0.12%",
            exact_quote="suppression below 0.12%",
            sub_question_id="SQ-1",
            confidence=ConfidenceLevel.VERIFIED,
        )

        synthesizer = SynthesizerAgent(llm=mock_llm)
        step = await synthesizer.execute(state)

        assert step.status == "completed"
        assert state.status == ResearchStatus.SYNTHESIZING
        assert state.budget.current_cost_usd > 0.0

    @pytest.mark.asyncio
    async def test_citation_auditor_renumbers_and_builds_bibliography(self) -> None:
        source = Source.create(
            url="https://arxiv.org/abs/2401.00001",
            title="Scalable Surface Codes",
            cleaned_markdown="Suppression below 0.12% was verified experimentally in the lab.",
        )
        evidence = Evidence(
            evidence_id="EV-001",
            source_id=source.source_id,
            source_url=source.canonical_url,
            claim="Threshold crossing measured below 0.12%",
            exact_quote="Suppression below 0.12% was verified",
            sub_question_id="SQ-1",
            confidence=ConfidenceLevel.VERIFIED,
        )

        state = ResearchState(initial_query="Quantum Error Correction")
        state.add_source(source)
        state.add_evidence(evidence)

        draft = DraftReportPayload(
            title="Surface Code Viability",
            executive_summary="Hardware tests confirmed scaling [EV-001].",
            sections=[
                DraftSection(
                    title="Detailed Analysis",
                    content="Physical trials report [EV-001] as the milestone threshold.",
                )
            ],
        )

        auditor = CitationAuditorAgent()
        step = await auditor.execute(state, draft_report=draft)

        assert step.status == "completed"
        assert state.status == ResearchStatus.COMPLETED
        assert state.final_report is not None
        assert state.final_report.title == "Surface Code Viability"

        # Check inline citation was converted from [EV-001] to [1]
        assert "[1]" in state.final_report.executive_summary
        assert "[1]" in state.final_report.sections[0].content
        assert "[EV-001]" not in state.final_report.sections[0].content

        # Check bibliography entry
        assert len(state.final_report.bibliography) == 1
        citation = state.final_report.bibliography[0]
        assert citation.numeric_index == 1
        assert citation.url == source.canonical_url
        assert citation.title == "Scalable Surface Codes"
        assert citation.verbatim_quote_anchor == evidence.exact_quote

        # Check markdown generation
        md = state.final_report.to_markdown()
        assert "# Surface Code Viability" in md
        assert '[1] "Scalable Surface Codes".' in md

    @pytest.mark.asyncio
    async def test_citation_auditor_strips_hallucinated_tokens(self) -> None:
        state = ResearchState(initial_query="Test query")
        draft = DraftReportPayload(
            title="Report with Hallucination",
            executive_summary="Valid claim here, but this cited token does not exist [EV-FAKE-99].",
            sections=[
                DraftSection(
                    title="Section 1",
                    content="Another sentence citing non-existent [EV-GHOST].",
                )
            ],
        )

        auditor = CitationAuditorAgent()
        step = await auditor.execute(state, draft_report=draft)

        assert step.status == "completed"
        assert state.final_report is not None
        # Hallucinated markers should be stripped and replaced with [Unverified Claim]
        assert "[Unverified Claim]" in state.final_report.executive_summary
        assert "[Unverified Claim]" in state.final_report.sections[0].content
        assert "[EV-FAKE-99]" not in state.final_report.executive_summary
        assert "[EV-GHOST]" not in state.final_report.sections[0].content

        # Check that auditor logged limitations
        assert any("ungrounded claim tokens" in lim for lim in state.final_report.known_limitations)
        assert len(state.final_report.bibliography) == 0
