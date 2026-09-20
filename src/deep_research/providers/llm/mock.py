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
            # Construct default instance if possible
            result = response_model.model_validate({})

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
