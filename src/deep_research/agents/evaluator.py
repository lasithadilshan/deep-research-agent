"""Evaluator agent assessing source credibility and filtering content quality."""

from typing import Any
from urllib.parse import urlparse

from deep_research.agents.base import BaseAgent
from deep_research.models.source import Source, SourceType
from deep_research.models.state import ResearchState, StepResult

MIN_CONTENT_LENGTH = 150
BLOCKED_PATTERNS = [
    "access denied",
    "403 forbidden",
    "enable javascript to continue",
    "attention required! | cloudflare",
    "just a moment...",
    "page not found",
    "404 not found",
]

ACADEMIC_DOMAINS = {
    "arxiv.org",
    "nature.com",
    "science.org",
    "cell.com",
    "ieee.org",
    "nih.gov",
    "ncbi.nlm.nih.gov",
    "acm.org",
    "springer.com",
}


class EvaluatorAgent(BaseAgent):
    """Evaluates raw sources, enriches credibility metadata, and filters noise."""

    def __init__(self) -> None:
        super().__init__(agent_name="EvaluatorAgent", llm=None)

    async def run(self, state: ResearchState, **kwargs: Any) -> StepResult:
        """Evaluate all sources in state.sources and prune unusable items."""
        initial_count = len(state.sources)
        valid_sources: dict[str, Source] = {}
        rejected_count = 0

        for source_id, source in state.sources.items():
            is_valid, reason = self.evaluate_source(source)
            if is_valid:
                valid_sources[source_id] = source
            else:
                rejected_count += 1
                state.record_audit(f"Evaluator rejected source '{source.canonical_url}': {reason}")

        # Update state sources with filtered set
        state.sources = valid_sources

        return StepResult(
            agent_name=self.agent_name,
            status="completed",
            summary=f"Evaluated {initial_count} sources: {len(valid_sources)} retained, {rejected_count} rejected",
            items_produced=len(valid_sources),
        )

    def evaluate_source(self, source: Source) -> tuple[bool, str]:
        """Verify content sufficiency, lack of anti-bot blockers, and domain classification."""
        content = source.cleaned_markdown or source.snippet or ""

        # Content length check
        if len(content.strip()) < MIN_CONTENT_LENGTH:
            return (
                False,
                f"Content length ({len(content.strip())} chars) below threshold ({MIN_CONTENT_LENGTH})",
            )

        # Anti-bot and error page check
        content_lower = content[:500].lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern in content_lower:
                return False, f"Anti-bot/error pattern detected: '{pattern}'"

        # Domain classification enrichment
        domain = urlparse(source.canonical_url).netloc.lower()
        if any(domain.endswith(tld) for tld in [".gov", ".edu", ".mil"]):
            source.source_type = SourceType.GOVERNMENT_REPORT
            source.credibility.is_tld_verified = True
        elif domain in ACADEMIC_DOMAINS:
            source.source_type = SourceType.ACADEMIC_PAPER
            source.credibility.is_tld_verified = True
        elif source.source_type == SourceType.UNKNOWN:
            source.source_type = (
                SourceType.NEWS_OUTLET if "news" in domain else SourceType.COMMUNITY_FORUM
            )

        return True, "Passed all quality criteria"
