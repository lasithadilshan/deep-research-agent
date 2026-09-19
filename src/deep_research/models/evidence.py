"""Atomic evidence models and grounding verification."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ConfidenceLevel(StrEnum):
    """Graded confidence based on source authority and independent corroboration."""

    LOW = "low"  # Single uncorroborated source or commercial marketing claim
    MEDIUM = "medium"  # Reputable general source or partially corroborated
    HIGH = "high"  # Multiple independent primary sources or official doc
    VERIFIED = "verified"  # Direct peer-reviewed scientific or statutory finding


class Evidence(BaseModel):
    """Atomic factual proposition extracted from a verified source passage."""

    evidence_id: str = Field(description="Unique identifier, e.g. EV-001")
    source_id: str = Field(description="Foreign key pointing to Source.source_id")
    source_url: str = Field(description="Direct URL to the originating source")
    claim: str = Field(description="Declarative factual statement extracted from passage")
    exact_quote: str = Field(
        description="Verbatim, uninterrupted substring from source text used for grounding"
    )
    context_passage: str = Field(
        default="", description="Broader paragraph or context surrounding the quote"
    )
    sub_question_id: str = Field(
        description="Identifier of the planned sub-question this evidence addresses"
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM, description="Evaluated confidence rating"
    )
    conflicting_evidence_ids: list[str] = Field(
        default_factory=list, description="List of evidence IDs that make contradictory assertions"
    )
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    def verify_quote_grounding(self, source_content: str) -> bool:
        """Verify that exact_quote exists verbatim in the source content."""
        if not self.exact_quote or not source_content:
            return False
        # Normalize whitespace for minor formatting differences
        normalized_quote = " ".join(self.exact_quote.split())
        normalized_source = " ".join(source_content.split())
        return normalized_quote in normalized_source
