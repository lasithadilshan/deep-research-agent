"""Synthesizer agent compiling verified evidence into structured research reports."""

from typing import Any

from pydantic import BaseModel, Field

from deep_research.agents.base import BaseAgent
from deep_research.core.exceptions import LLMProviderError
from deep_research.models.state import ResearchState, ResearchStatus, StepResult
from deep_research.providers.llm.base import BaseLLMProvider


class DraftSection(BaseModel):
    """Section within draft report containing [EV-xxx] inline markers."""

    title: str = Field(description="Descriptive section heading")
    content: str = Field(
        description="Detailed analytical narrative citing evidence using [EV-xxx] tokens"
    )


class DraftReportPayload(BaseModel):
    """Draft report schema emitted by synthesizer prior to citation audit."""

    title: str = Field(description="Comprehensive report title")
    executive_summary: str = Field(
        description="Executive summary synthesizing primary conclusions with [EV-xxx] markers"
    )
    sections: list[DraftSection] = Field(
        description="Multi-section body examining evidence and answering sub-questions"
    )
    known_limitations: list[str] = Field(
        default_factory=list,
        description="Explicit gaps, contradictions, or data uncertainties",
    )
    methodology_notes: str = Field(
        default="",
        description="Summary of analytical criteria and search strategy",
    )


SYNTHESIZER_SYSTEM_INSTRUCTION = """You are a Principal Research Scientist and Author.
Your mission is to synthesize verified research findings into an exhaustive, publication-grade report.

STRICT CITATION & GROUNDING CONSTRAINTS:
1. Every factual assertion, metric, comparison, or finding MUST cite its supporting evidence token: [EV-xxx].
2. You must ONLY cite evidence tokens provided in the prompt. NEVER invent or hallucinate evidence tokens.
3. If an important question lacks evidence, explicitly acknowledge it as an unverified gap or limitation.
4. Write in an authoritative, objective, scientific style with clear section headings.
5. Place citation markers directly after the factual statement, e.g. "The error threshold was 0.12% [EV-001]."
"""


class SynthesizerAgent(BaseAgent):
    """Composes structured scientific research report citing atomic evidence tokens."""

    def __init__(self, llm: BaseLLMProvider) -> None:
        super().__init__(agent_name="SynthesizerAgent", llm=llm)
        self.last_draft: DraftReportPayload | None = None

    async def run(self, state: ResearchState, **kwargs: Any) -> StepResult:
        if not self.llm:
            raise LLMProviderError("SynthesizerAgent requires an active LLM provider.")

        state.transition_to(
            ResearchStatus.SYNTHESIZING, "Composing research report from evidence pool"
        )

        evidence_entries: list[str] = []
        for ev_id, ev in state.evidence_pool.items():
            source = state.sources.get(ev.source_id)
            domain = source.credibility.domain if source else "unknown"
            evidence_entries.append(
                f"[{ev_id}] (Source: {domain})\n"
                f"  Claim: {ev.claim}\n"
                f'  Verbatim Quote: "{ev.exact_quote}"\n'
            )

        evidence_text = (
            "\n".join(evidence_entries) if evidence_entries else "No evidence available."
        )

        sub_q_text = ""
        if state.plan:
            sub_q_text = "\n".join(
                f"- {sq.question_id}: {sq.question}" for sq in state.plan.sub_questions
            )

        prompt = (
            f"Research Question: {state.initial_query}\n\n"
            f"Sub-Questions to Address:\n{sub_q_text}\n\n"
            f"AVAILABLE VERIFIED EVIDENCE POOL:\n"
            f"{evidence_text}\n\n"
            f"Synthesize an authoritative research report answering the research question. "
            f"Ground every claim using the provided [EV-xxx] tokens."
        )

        draft, usage = await self.llm.generate_structured(
            prompt=prompt,
            response_model=DraftReportPayload,
            system_instruction=SYNTHESIZER_SYSTEM_INSTRUCTION,
            temperature=0.2,
        )
        state.budget.record_llm_call(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
        )

        self.last_draft = draft
        summary = (
            f"Drafted report '{draft.title}' with {len(draft.sections)} sections "
            f"using {len(evidence_entries)} evidence pieces"
        )
        # Pass draft payload in kwargs/state for auditor
        state.audit_log.append(f"Synthesizer emitted draft: {draft.title}")

        return StepResult(
            agent_name=self.agent_name,
            status="completed",
            summary=summary,
            items_produced=len(draft.sections),
        )
