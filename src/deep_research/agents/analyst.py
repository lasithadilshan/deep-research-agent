"""Analyst agent performing cross-evidence synthesis, gap detection, and conflict analysis."""

from typing import Any

from pydantic import BaseModel, Field

from deep_research.agents.base import BaseAgent
from deep_research.models.evidence import ConfidenceLevel
from deep_research.models.state import Finding, ResearchState, ResearchStatus, StepResult
from deep_research.providers.llm.base import BaseLLMProvider


class IdentifiedConflict(BaseModel):
    """Contradiction detected between two or more evidence items."""

    topic: str = Field(description="Sub-topic or metric with conflicting evidence")
    conflicting_evidence_ids: list[str] = Field(description="IDs of opposing evidence claims")
    explanation: str = Field(description="Why these assertions conflict")
    resolution_query: str = Field(
        description="Targeted search query to arbitrate and resolve the conflict"
    )


class GapAnalysisOutput(BaseModel):
    """Output produced by analyst evaluating coverage and missing evidence."""

    unresolved_questions: list[str] = Field(
        default_factory=list,
        description="Sub-questions that still lack strong evidence or corroboration",
    )
    conflicts: list[IdentifiedConflict] = Field(
        default_factory=list,
        description="Detected factual contradictions",
    )
    suggested_follow_up_queries: list[str] = Field(
        default_factory=list,
        description="Targeted follow-up search queries for the next iteration",
    )


ANALYST_SYSTEM_INSTRUCTION = """You are a Principal Intelligence and Research Analyst.
Your task is to cross-examine accumulated evidence, evaluate factual coverage, detect contradictions between sources, and identify critical knowledge gaps.

ANALYSIS GUIDELINES:
1. Examine claims made across independent sources. If two sources assert conflicting metrics or conclusions, explicitly flag a conflict.
2. For each conflict, formulate a high-precision resolution query designed to find official filings, primary data, or consensus benchmarks.
3. Identify which sub-questions remain poorly substantiated or unaddressed.
4. Generate focused follow-up queries that target specific missing data points.
"""


class AnalystAgent(BaseAgent):
    """Cross-examines evidence, identifies contradictions, and generates follow-up queries for deep iterations."""

    def __init__(self, llm: BaseLLMProvider) -> None:
        super().__init__(agent_name="AnalystAgent", llm=llm)
        self.last_analysis: GapAnalysisOutput | None = None

    async def run(self, state: ResearchState, **kwargs: Any) -> StepResult:
        state.transition_to(
            ResearchStatus.ANALYZING, "Analyzing evidence density, gaps, and contradictions"
        )

        if not state.evidence_pool:
            return StepResult(
                agent_name=self.agent_name,
                status="completed",
                summary="Evidence pool empty; gap analysis skipped.",
                items_produced=0,
            )

        # 1. Compute empirical evidence density per sub-question
        sub_questions = state.plan.sub_questions if state.plan else []
        unresolved_sqs: list[str] = []

        for sq in sub_questions:
            density_score = 0.0
            source_domains: set[str] = set()

            for ev_id in sq.evidence_ids:
                if ev_id in state.evidence_pool:
                    ev = state.evidence_pool[ev_id]
                    weight = (
                        1.0
                        if ev.confidence in {ConfidenceLevel.HIGH, ConfidenceLevel.VERIFIED}
                        else 0.5
                    )
                    density_score += weight
                    source = state.sources.get(ev.source_id)
                    if source:
                        source_domains.add(source.credibility.domain)

            # A sub-question is answered if density >= 1.0 and at least 1 reliable source exists
            if density_score >= 1.0 and len(source_domains) >= 1:
                sq.is_answered = True
            else:
                sq.is_answered = False
                unresolved_sqs.append(sq.question)

        # 2. LLM cross-examination for contradictions and follow-up query formulation
        evidence_summary_lines: list[str] = []
        for ev_id, ev in state.evidence_pool.items():
            evidence_summary_lines.append(f"[{ev_id}] {ev.claim} (Quote: '{ev.exact_quote[:80]}')")

        prompt = (
            f"Primary Research Question: {state.initial_query}\n\n"
            f"Unresolved Sub-Questions:\n" + "\n".join(f"- {q}" for q in unresolved_sqs) + "\n\n"
            "CURRENT EVIDENCE POOL:\n" + "\n".join(evidence_summary_lines) + "\n\n"
            "Analyze the evidence pool. Identify any conflicting assertions, verify which sub-questions remain "
            "unresolved, and generate precise follow-up search queries to fill gaps."
        )

        try:
            analysis, usage = await self.llm.generate_structured(  # type: ignore[union-attr]
                prompt=prompt,
                response_model=GapAnalysisOutput,
                system_instruction=ANALYST_SYSTEM_INSTRUCTION,
                temperature=0.1,
            )
            self.last_analysis = analysis
            state.budget.record_llm_call(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=usage.cost_usd,
            )

            # Record unresolved gaps and conflicts in state
            state.unresolved_gaps = list(set(unresolved_sqs + analysis.unresolved_questions))

            for conflict in analysis.conflicts:
                conflict_desc = f"Conflict in '{conflict.topic}': {conflict.explanation} (IDs: {conflict.conflicting_evidence_ids})"
                if conflict_desc not in state.identified_conflicts:
                    state.identified_conflicts.append(conflict_desc)
                state.record_audit(f"Analyst flagged: {conflict_desc}")

            # Synthesize atomic Findings
            findings: list[Finding] = []
            for i, sq in enumerate(sub_questions, 1):
                if sq.evidence_ids:
                    findings.append(
                        Finding(
                            finding_id=f"FND-{i:03d}",
                            topic=sq.question,
                            summary=f"Evidence gathered addressing '{sq.question}' across {len(sq.evidence_ids)} citations.",
                            supporting_evidence_ids=list(sq.evidence_ids),
                            confidence=(
                                ConfidenceLevel.HIGH if sq.is_answered else ConfidenceLevel.MEDIUM
                            ),
                        )
                    )
            state.findings = findings

            # Return follow-up queries for deep research loop
            follow_ups = list(analysis.suggested_follow_up_queries)
            for conflict in analysis.conflicts:
                if conflict.resolution_query and conflict.resolution_query not in follow_ups:
                    follow_ups.append(conflict.resolution_query)

            summary = (
                f"Completed analysis: {len(findings)} findings compiled, "
                f"{len(state.unresolved_gaps)} gaps, {len(analysis.conflicts)} conflicts detected, "
                f"{len(follow_ups)} follow-up queries formulated"
            )
            return StepResult(
                agent_name=self.agent_name,
                status="completed",
                summary=summary,
                items_produced=len(findings),
            )

        except Exception as e:
            self.logger.warning("analyst_structured_failed", error=str(e))
            state.record_audit(f"Analyst cross-examination failed: {e}")
            fallback_analysis = GapAnalysisOutput(
                unresolved_questions=unresolved_sqs,
                conflicts=[],
                suggested_follow_up_queries=[
                    f"{q} authoritative research" for q in unresolved_sqs[:2]
                ],
            )
            self.last_analysis = fallback_analysis
            state.unresolved_gaps = unresolved_sqs
            return StepResult(
                agent_name=self.agent_name,
                status="completed_fallback",
                summary=f"Analysis fallback completed with {len(unresolved_sqs)} gaps",
                items_produced=0,
            )
