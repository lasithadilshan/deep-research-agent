"""Test suite configuration and shared fixtures."""

import pytest

from deep_research.models import (
    BudgetTracker,
    ConfidenceLevel,
    Evidence,
    ResearchMode,
    ResearchState,
    Source,
    SourceType,
)


@pytest.fixture
def sample_source() -> Source:
    """Fixture returning a standard verified research source."""
    return Source.create(
        url="https://arxiv.org/abs/2401.12345?utm_source=twitter&ref=newsletter",
        title="Scalable Quantum Fault-Tolerance via Surface Codes",
        snippet="A study demonstrating physical threshold improvements in surface codes.",
        source_type=SourceType.ACADEMIC_PAPER,
        cleaned_markdown="We demonstrate that physical error rates below 0.5% achieve exponential suppression.",
        has_author=True,
        trust_indicators=["peer_reviewed", "preprint_repository"],
    )


@pytest.fixture
def sample_evidence(sample_source: Source) -> Evidence:
    """Fixture returning an atomic evidence record tied to sample_source."""
    return Evidence(
        evidence_id="EV-001",
        source_id=sample_source.source_id,
        source_url=sample_source.canonical_url,
        claim="Physical error rates below 0.5% achieve exponential suppression in surface codes.",
        exact_quote="physical error rates below 0.5% achieve exponential suppression",
        context_passage="We demonstrate that physical error rates below 0.5% achieve exponential suppression.",
        sub_question_id="SQ-1",
        confidence=ConfidenceLevel.VERIFIED,
    )


@pytest.fixture
def sample_state() -> ResearchState:
    """Fixture returning an initialized ResearchState."""
    return ResearchState(
        initial_query="What are the latest breakthroughs in surface code error correction?",
        mode=ResearchMode.STANDARD,
        budget=BudgetTracker(max_budget_usd=2.50),
    )
