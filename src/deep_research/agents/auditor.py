"""Citation auditor agent validating and renumbering citations into final report."""

import re
from typing import Any

from deep_research.agents.base import BaseAgent
from deep_research.agents.synthesizer import DraftReportPayload
from deep_research.models.report import Citation, ResearchReport, Section
from deep_research.models.state import ResearchState, ResearchStatus, StepResult

CITATION_TOKEN_REGEX = re.compile(r"\[(EV-[a-zA-Z0-9_-]+)\]")


class CitationAuditorAgent(BaseAgent):
    """Audits draft report, verifies citation grounding, and converts [EV-xxx] tokens to [N]."""

    def __init__(self) -> None:
        super().__init__(agent_name="CitationAuditorAgent", llm=None)

    async def run(
        self,
        state: ResearchState,
        draft_report: DraftReportPayload | None = None,
        **kwargs: Any,
    ) -> StepResult:
        if not draft_report:
            raise ValueError("CitationAuditorAgent requires 'draft_report' parameter.")

        state.transition_to(
            ResearchStatus.AUDITING, "Auditing citation integrity and building bibliography"
        )

        # Map distinct evidence IDs to sequential numeric indices
        evidence_to_citation_index: dict[str, int] = {}
        citations: list[Citation] = []
        hallucinated_citations: list[str] = []
        next_citation_idx = 1

        def replace_evidence_token(match: re.Match[str]) -> str:
            nonlocal next_citation_idx
            ev_id = match.group(1)

            if ev_id not in state.evidence_pool:
                hallucinated_citations.append(ev_id)
                state.record_audit(
                    f"Auditor stripped hallucinated evidence token [{ev_id}]: not in evidence pool."
                )
                return "[Unverified Claim]"

            if ev_id not in evidence_to_citation_index:
                evidence_to_citation_index[ev_id] = next_citation_idx
                evidence = state.evidence_pool[ev_id]
                source = state.sources.get(evidence.source_id)

                citations.append(
                    Citation(
                        numeric_index=next_citation_idx,
                        source_id=evidence.source_id,
                        url=evidence.source_url,
                        title=source.title if source else "External Source",
                        author=None,
                        published_date=(
                            source.credibility.published_date.strftime("%Y-%m-%d")
                            if source and source.credibility.published_date
                            else None
                        ),
                        accessed_date=evidence.extracted_at.strftime("%Y-%m-%d"),
                        verbatim_quote_anchor=evidence.exact_quote,
                    )
                )
                next_citation_idx += 1

            return f"[{evidence_to_citation_index[ev_id]}]"

        # Transform executive summary
        audited_summary = CITATION_TOKEN_REGEX.sub(
            replace_evidence_token, draft_report.executive_summary
        )

        # Transform each section
        audited_sections: list[Section] = []
        for sec in draft_report.sections:
            audited_content = CITATION_TOKEN_REGEX.sub(replace_evidence_token, sec.content)

            # Find all numbers cited in this section
            cited_nums = [int(n) for n in re.findall(r"\[(\d+)\]", audited_content)]
            audited_sections.append(
                Section(
                    title=sec.title,
                    content=audited_content,
                    cited_numbers=sorted(set(cited_nums)),
                )
            )

        limitations = list(draft_report.known_limitations)
        if hallucinated_citations:
            limitations.append(
                f"Auditor detected and flagged {len(hallucinated_citations)} ungrounded claim tokens "
                f"lacking underlying evidence: {', '.join(hallucinated_citations)}"
            )

        final_report = ResearchReport(
            title=draft_report.title,
            executive_summary=audited_summary,
            sections=audited_sections,
            bibliography=citations,
            research_methodology=draft_report.methodology_notes
            or (
                f"Multi-source investigation using Google Gemini 3.8 Flash across "
                f"{len(state.sources)} evaluated sources and {len(state.evidence_pool)} extracted evidence items."
            ),
            known_limitations=limitations,
            total_sources_consulted=len(state.sources),
            total_evidence_pieces=len(state.evidence_pool),
        )

        state.final_report = final_report
        state.transition_to(
            ResearchStatus.COMPLETED, f"Report published with {len(citations)} citations"
        )

        summary = (
            f"Audited report '{final_report.title}': {len(citations)} citations verified, "
            f"{len(hallucinated_citations)} hallucinations stripped"
        )
        return StepResult(
            agent_name=self.agent_name,
            status="completed",
            summary=summary,
            items_produced=len(citations),
        )
