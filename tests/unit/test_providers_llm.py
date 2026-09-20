"""Unit tests for LLM provider abstraction, Mock provider, and Gemini provider."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from deep_research.core.exceptions import (
    ConfigurationError,
    LLMAuthenticationError,
    LLMRateLimitError,
)
from deep_research.providers.llm import (
    BaseLLMProvider,
    GeminiProvider,
    MockLLMProvider,
    get_llm_provider,
    list_llm_providers,
)


class DummyPlan(BaseModel):
    objective: str
    steps: list[str]


class TestMockLLMProvider:
    @pytest.mark.asyncio
    async def test_text_generation_queued_and_default(self) -> None:
        mock = MockLLMProvider()
        mock.queue_text_response("First queued response")

        text1, usage1 = await mock.generate_text("Hello world")
        assert text1 == "First queued response"
        assert usage1.prompt_tokens > 0
        assert usage1.completion_tokens > 0
        assert usage1.cost_usd > 0.0

        # Now test default fallback when queue is empty
        text2, usage2 = await mock.generate_text("Second query that has no queued item")
        assert "Mock response to:" in text2
        assert usage2.prompt_tokens > 0

    @pytest.mark.asyncio
    async def test_structured_generation_queued(self) -> None:
        mock = MockLLMProvider()
        expected = DummyPlan(objective="Investigate Fusion", steps=["Search papers", "Synthesize"])
        mock.queue_structured_response(expected)

        plan, usage = await mock.generate_structured("Plan fusion research", DummyPlan)
        assert plan == expected
        assert plan.objective == "Investigate Fusion"
        assert usage.prompt_tokens > 0

    @pytest.mark.asyncio
    async def test_structured_generation_type_mismatch_raises(self) -> None:
        mock = MockLLMProvider()

        class OtherModel(BaseModel):
            value: int

        mock.queue_structured_response(OtherModel(value=42))
        with pytest.raises(ValueError, match="does not match expected"):
            await mock.generate_structured("Prompt", DummyPlan)

    @pytest.mark.asyncio
    async def test_error_queue_raises(self) -> None:
        mock = MockLLMProvider()
        mock.queue_error(LLMRateLimitError("Quota reached"))

        with pytest.raises(LLMRateLimitError, match="Quota reached"):
            await mock.generate_text("Test prompt")

    def test_cost_calculation(self) -> None:
        mock = MockLLMProvider()
        # 1,000,000 prompt tokens ($0.15) + 1,000,000 completion tokens ($0.60) = $0.75
        cost = mock.calculate_cost(1_000_000, 1_000_000)
        assert cost == 0.75


class TestLLMProviderFactory:
    def test_list_providers(self) -> None:
        providers = list_llm_providers()
        assert "mock" in providers
        assert "gemini" in providers

    def test_get_registered_provider(self) -> None:
        provider = get_llm_provider("mock", model_name="custom-mock")
        assert isinstance(provider, BaseLLMProvider)
        assert provider.model_name == "custom-mock"

    def test_case_insensitive_lookup(self) -> None:
        provider = get_llm_provider("MocK")
        assert isinstance(provider, MockLLMProvider)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="Unknown LLM provider 'non_existent'"):
            get_llm_provider("non_existent")


class TestGeminiProvider:
    def test_missing_api_key_raises_auth_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(LLMAuthenticationError, match="Gemini API key not found"):
            GeminiProvider(api_key=None)

    def test_token_and_cost_estimation(self) -> None:
        mock_client = MagicMock()
        provider = GeminiProvider(
            api_key="AIzaSyFakeKeyForTesting12345678901234", client=mock_client
        )

        assert provider.count_tokens("12345678") == 2
        # 1M prompt ($0.15) + 1M completion ($0.60) = $0.75
        cost = provider.calculate_cost(1_000_000, 1_000_000)
        assert cost == 0.75

    @pytest.mark.asyncio
    async def test_gemini_generate_text_with_mocked_client(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is a synthesized summary."
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        provider = GeminiProvider(
            api_key="AIzaSyFakeKeyForTesting12345678901234", client=mock_client
        )
        text, usage = await provider.generate_text("Prompt question")

        assert text == "This is a synthesized summary."
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.cost_usd > 0.0

    @pytest.mark.asyncio
    async def test_gemini_generate_structured_with_mocked_client(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            '{"objective": "Advance Quantum Science", "steps": ["Read arxiv", "Simulate"]}'
        )
        mock_response.usage_metadata.prompt_token_count = 120
        mock_response.usage_metadata.candidates_token_count = 40

        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        provider = GeminiProvider(
            api_key="AIzaSyFakeKeyForTesting12345678901234", client=mock_client
        )
        obj, usage = await provider.generate_structured("Give me plan", DummyPlan)

        assert isinstance(obj, DummyPlan)
        assert obj.objective == "Advance Quantum Science"
        assert obj.steps == ["Read arxiv", "Simulate"]
        assert usage.prompt_tokens == 120

    @pytest.mark.asyncio
    async def test_gemini_fallback_usage_when_metadata_missing(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Generated fallback text"
        mock_response.usage_metadata = None
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        provider = GeminiProvider(
            api_key="AIzaSyFakeKeyForTesting12345678901234", client=mock_client
        )
        text, usage = await provider.generate_text("Short prompt")
        assert text == "Generated fallback text"
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0

    @pytest.mark.asyncio
    async def test_gemini_structured_invalid_json_raises(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Not valid JSON at all"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        provider = GeminiProvider(
            api_key="AIzaSyFakeKeyForTesting12345678901234", client=mock_client
        )
        from deep_research.core.exceptions import LLMProviderError

        with pytest.raises(LLMProviderError, match="Failed to parse structured JSON"):
            await provider.generate_structured("Give me plan", DummyPlan)

    def test_gemini_handle_api_error_mappings(self) -> None:
        from google.genai.errors import APIError

        from deep_research.core.exceptions import (
            LLMAuthenticationError,
            LLMContextLengthExceededError,
            LLMRateLimitError,
        )

        mock_client = MagicMock()
        provider = GeminiProvider(
            api_key="AIzaSyFakeKeyForTesting12345678901234", client=mock_client
        )

        # Rate limit
        err_429 = APIError(429, "Resource has been exhausted (e.g. check quota)")
        with pytest.raises(LLMRateLimitError):
            provider._handle_api_error(err_429)

        # Auth error
        err_401 = APIError(401, "API key not valid")
        with pytest.raises(LLMAuthenticationError):
            provider._handle_api_error(err_401)

        # Context length error
        err_ctx = APIError(400, "Maximum context length exceeded")
        with pytest.raises(LLMContextLengthExceededError):
            provider._handle_api_error(err_ctx)
