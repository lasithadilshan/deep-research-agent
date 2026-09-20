"""Deterministic Mock LLM provider for testing without external API calls."""

from typing import Any, TypeVar

from pydantic import BaseModel

from deep_research.models.cost import TokenUsage
from deep_research.providers.llm.base import BaseLLMProvider
from deep_research.providers.llm.factory import register_llm_provider

T = TypeVar("T", bound=BaseModel)


@register_llm_provider("mock")
class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider delivering pre-queued responses or deterministic outputs."""

    def __init__(self, model_name: str = "mock-model") -> None:
        super().__init__(model_name=model_name)
        self.text_queue: list[str] = []
        self.structured_queue: list[BaseModel] = []
        self.error_queue: list[Exception] = []
        self.calls: list[dict[str, Any]] = []

    def queue_text_response(self, text: str) -> None:
        """Enqueue a string response for generate_text."""
        self.text_queue.append(text)

    def queue_structured_response(self, obj: BaseModel) -> None:
        """Enqueue a Pydantic model response for generate_structured."""
        self.structured_queue.append(obj)

    def queue_error(self, exc: Exception) -> None:
        """Enqueue an exception to be raised on next call."""
        self.error_queue.append(exc)

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> tuple[str, TokenUsage]:
        self.calls.append(
            {
                "type": "text",
                "prompt": prompt,
                "system_instruction": system_instruction,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if self.error_queue:
            raise self.error_queue.pop(0)

        if self.text_queue:
            response_text = self.text_queue.pop(0)
        else:
            response_text = f"Mock response to: {prompt[:50]}"

        prompt_tokens = self.count_tokens(prompt)
        completion_tokens = self.count_tokens(response_text)
        cost = self.calculate_cost(prompt_tokens, completion_tokens)
        return response_text, TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.1,
    ) -> tuple[T, TokenUsage]:
        self.calls.append(
            {
                "type": "structured",
                "prompt": prompt,
                "response_model": response_model,
                "system_instruction": system_instruction,
                "temperature": temperature,
            }
        )

        if self.error_queue:
            raise self.error_queue.pop(0)

        if self.structured_queue:
            item = self.structured_queue.pop(0)
            if not isinstance(item, response_model):
                raise ValueError(
                    f"Queued response {type(item)} does not match expected {response_model}"
                )
            result = item
        else:
            result = self._generate_synthetic_structured(response_model, prompt)

        prompt_tokens = self.count_tokens(prompt)
        completion_tokens = 50
        cost = self.calculate_cost(prompt_tokens, completion_tokens)
        return result, TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        )

    def count_tokens(self, text: str) -> int:
        # Standard fast approximation: ~4 characters per token
        return max(1, len(text) // 4)

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        # Mock pricing: $0.15 / 1M prompt, $0.60 / 1M completion
        cost = (prompt_tokens * 0.15 / 1_000_000) + (completion_tokens * 0.60 / 1_000_000)
        return round(cost, 6)

    def _generate_synthetic_structured(self, model_cls: type[T], prompt: str) -> T:
        """Construct synthetic valid instances for common research schemas."""
        name = model_cls.__name__

        if name == "GeneratedResearchPlan":
            from deep_research.agents.planner import GeneratedResearchPlan, GeneratedSubQuestion

            return GeneratedResearchPlan(  # type: ignore[return-value]
                primary_objective="Autonomous Scientific Investigation",
                hypotheses=["The investigated topic exhibits strong empirical viability."],
                sub_questions=[
                    GeneratedSubQuestion(
                        question_id="SQ-1",
                        question="What are the foundational metrics and latest developments?",
                        rationale="Establish baseline metrics",
                        target_queries=["research topic state of the art"],
                    )
                ],
                initial_search_queries=["research topic state of the art"],
            )

        if name == "ExtractedEvidenceBatch":
            from deep_research.agents.extractor import ExtractedEvidenceBatch, RawExtractedClaim
            from deep_research.models.evidence import ConfidenceLevel

            # Look for lines in prompt to use as quote
            quote = "findings regarding"
            if "findings regarding" not in prompt:
                # Pick any short word sequence from prompt
                words = prompt.split()
                quote = " ".join(words[5:10]) if len(words) > 10 else "research"

            return ExtractedEvidenceBatch(  # type: ignore[return-value]
                claims=[
                    RawExtractedClaim(
                        claim="Synthesized finding from retrieved evidence.",
                        exact_quote=quote,
                        confidence=ConfidenceLevel.HIGH,
                    )
                ]
            )

        if name == "DraftReportPayload":
            from deep_research.agents.synthesizer import DraftReportPayload, DraftSection

            return DraftReportPayload(  # type: ignore[return-value]
                title="Synthesized Investigation Report",
                executive_summary="Empirical evidence validates the primary hypothesis [EV-001].",
                sections=[
                    DraftSection(
                        title="Empirical Findings",
                        content="Detailed investigation results substantiate the conclusions [EV-001].",
                    )
                ],
                known_limitations=["Experimental scope restricted to laboratory benchmarks."],
            )

        try:
            return model_cls.model_validate({})
        except Exception:
            return model_cls.model_construct()
