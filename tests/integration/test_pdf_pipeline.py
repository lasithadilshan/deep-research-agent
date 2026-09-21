"""Integration test verifying end-to-end research loop on academic PDF documents."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from deep_research.agents.auditor import CitationAuditorAgent
from deep_research.agents.evaluator import EvaluatorAgent
from deep_research.agents.extractor import ExtractorAgent
from deep_research.agents.synthesizer import SynthesizerAgent
from deep_research.models.cost import BudgetTracker
from deep_research.models.plan import ResearchMode, ResearchPlan, SubQuestion
from deep_research.models.source import Source, SourceType
from deep_research.models.state import ResearchState
from deep_research.providers.llm.mock import MockLLMProvider
from deep_research.tools.pdf_parser import PDFParser
from deep_research.tools.web_fetcher import WebFetcher


@pytest.mark.asyncio
async def test_pdf_ingestion_and_evidence_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Generate sample PDF text
    pdf_text = (
        "Fault-Tolerant Quantum Error Correction with Surface Codes.\n\n"
        "Abstract: We demonstrate that rotated surface codes achieve a logical error threshold "
        "below 0.1% using superconducting transmon architectures. "
        "The physical error rate was verified at 0.08% per gate cycle across 72 qubits."
    )

    # 2. Mock HTTP download of PDF
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/pdf"}
    # Use dummy PDF bytes with our parser
    mock_resp.content = b"%PDF-1.4 header\nstream\n" + pdf_text.encode("latin-1")
    mock_client.get.return_value = mock_resp

    fetcher = WebFetcher(client=mock_client)
    # Mock PDFParser to return our test text directly
    mock_parse = MagicMock(
        return_value=MagicMock(
            text=pdf_text,
            title="Fault-Tolerant Quantum Error Correction",
            author="Alice Cooper",
            page_count=5,
        )
    )
    monkeypatch.setattr(PDFParser, "parse_bytes", mock_parse)

    doc = await fetcher.fetch_document("https://arxiv.org/pdf/2403.01234.pdf", validate_ssrf=False)
    assert doc.is_pdf is True
    assert "rotated surface codes achieve a logical error threshold" in doc.content

    # 3. Create Source from PDF content
    source = Source.create(
        url="https://arxiv.org/pdf/2403.01234.pdf",
        title="Fault-Tolerant Quantum Error Correction",
        snippet="Threshold below 0.1%",
        source_type=SourceType.ACADEMIC_PAPER,
        cleaned_markdown=pdf_text,
    )
    assert source.source_type == SourceType.ACADEMIC_PAPER
    assert source.credibility.is_tld_verified is True  # arxiv.org is a verified domain

    # 4. Pipeline state with plan
    state = ResearchState(
        initial_query="Quantum surface code thresholds",
        mode=ResearchMode.QUICK,
        budget=BudgetTracker(max_budget_usd=1.0),
    )
    state.plan = ResearchPlan(
        primary_objective="Evaluate surface code thresholds",
        sub_questions=[
            SubQuestion(
                question_id="SQ-1",
                question="What is the logical error threshold achieved with surface codes?",
                rationale="Threshold verification",
            )
        ],
        initial_search_queries=["quantum surface code thresholds"],
        planned_mode=ResearchMode.QUICK,
    )
    state.add_source(source)

    # 5. Evaluate source
    evaluator = EvaluatorAgent()
    await evaluator.execute(state)
    assert source.source_id in state.sources

    # 6. Extract evidence with Mock LLM
    mock_llm = MockLLMProvider()
    extractor = ExtractorAgent(llm=mock_llm)
    await extractor.execute(state)

    # 7. Synthesize and audit
    synthesizer = SynthesizerAgent(llm=mock_llm)
    await synthesizer.execute(state)
    draft = synthesizer.last_draft

    auditor = CitationAuditorAgent()
    await auditor.execute(state, draft_report=draft)

    assert state.final_report is not None
    assert state.final_report.total_sources_consulted == 1
