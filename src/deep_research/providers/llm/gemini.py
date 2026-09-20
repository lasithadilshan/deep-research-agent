"""Google Gemini 3.8 Flash LLM provider implementation."""

import json
from typing import Any, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

from deep_research.config.settings import get_settings
from deep_research.core.exceptions import (
    LLMAuthenticationError,
    LLMContextLengthExceededError,
    LLMProviderError,
    LLMRateLimitError,
)
from deep_research.models.cost import TokenUsage
from deep_research.providers.llm.base import BaseLLMProvider
from deep_research.providers.llm.factory import register_llm_provider

T = TypeVar("T", bound=BaseModel)

# Gemini 3.8 Flash pricing: $0.15 / 1M prompt tokens, $0.60 / 1M completion tokens
INPUT_COST_PER_MILLION = 0.15
OUTPUT_COST_PER_MILLION = 0.60


@register_llm_provider("gemini")
class GeminiProvider(BaseLLMProvider):
    """Production provider for Google Gemini models using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        client: genai.Client | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.gemini_api_key
        resolved_model = model_name or settings.gemini_model or "gemini-3.8-flash"

        super().__init__(model_name=resolved_model)

        if not resolved_key and client is None:
            raise LLMAuthenticationError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable or pass api_key."
            )

        self._client = client or genai.Client(api_key=resolved_key)

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> tuple[str, TokenUsage]:
        """Generate text using Gemini 3.8 Flash."""
        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            text = response.text or ""
            usage = self._extract_usage(response, prompt=prompt, completion=text)
            return text, usage

        except genai_errors.APIError as e:
            self._handle_api_error(e)
            raise LLMProviderError(f"Gemini API error: {e}") from e
        except Exception as e:
            raise LLMProviderError(f"Unexpected error calling Gemini: {e}") from e

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.1,
    ) -> tuple[T, TokenUsage]:
        """Enforce strict Pydantic schema decoding via Gemini native response_schema."""
        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_model,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            raw_json = response.text or "{}"
            parsed_data = json.loads(raw_json)
            validated_obj = response_model.model_validate(parsed_data)
            usage = self._extract_usage(response, prompt=prompt, completion=raw_json)
            return validated_obj, usage

        except genai_errors.APIError as e:
            self._handle_api_error(e)
            raise LLMProviderError(f"Gemini API error: {e}") from e
        except json.JSONDecodeError as e:
            raise LLMProviderError(
                f"Failed to parse structured JSON from Gemini response: {e}. Raw content: {raw_json[:200]}"
            ) from e
        except Exception as e:
            raise LLMProviderError(f"Error during structured generation: {e}") from e

    def count_tokens(self, text: str) -> int:
        """Estimate token count for Gemini text (approx 4 chars/token)."""
        return max(1, len(text) // 4)

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate exact USD cost based on Gemini Flash pricing."""
        cost = (prompt_tokens * INPUT_COST_PER_MILLION / 1_000_000) + (
            completion_tokens * OUTPUT_COST_PER_MILLION / 1_000_000
        )
        return round(cost, 6)

    def _extract_usage(self, response: Any, prompt: str, completion: str) -> TokenUsage:
        """Extract exact token usage metadata or calculate fallback estimate."""
        prompt_tokens = 0
        completion_tokens = 0

        metadata = getattr(response, "usage_metadata", None)
        if metadata:
            prompt_tokens = getattr(metadata, "prompt_token_count", 0) or 0
            completion_tokens = getattr(metadata, "candidates_token_count", 0) or 0

        if prompt_tokens == 0:
            prompt_tokens = self.count_tokens(prompt)
        if completion_tokens == 0:
            completion_tokens = self.count_tokens(completion)

        cost = self.calculate_cost(prompt_tokens, completion_tokens)
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        )

    def _handle_api_error(self, err: genai_errors.APIError) -> None:
        """Map Gemini API exceptions to unified domain exceptions."""
        code = getattr(err, "code", None)
        message = str(err).lower()

        if code == 429 or "quota" in message or "rate limit" in message:
            raise LLMRateLimitError(f"Gemini rate limit exceeded: {err}") from err
        if code in {401, 403} or "unauthenticated" in message or "api key" in message:
            raise LLMAuthenticationError(f"Gemini authentication failed: {err}") from err
        if "context length" in message or "maximum context" in message:
            raise LLMContextLengthExceededError(f"Gemini context length exceeded: {err}") from err
