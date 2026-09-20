"""Abstract base protocol for LLM backends."""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from deep_research.models.cost import TokenUsage

T = TypeVar("T", bound=BaseModel)


class BaseLLMProvider(ABC):
    """Abstract interface defining required capabilities of an LLM provider."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> tuple[str, TokenUsage]:
        """Generate unstructured text completion.

        Returns tuple of (response_text, token_usage).
        """
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.1,
    ) -> tuple[T, TokenUsage]:
        """Generate structured output adhering to a Pydantic schema.

        Returns tuple of (parsed_pydantic_instance, token_usage).
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate or compute token count for given text."""
        pass

    @abstractmethod
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate dollar cost of inference based on token usage."""
        pass
