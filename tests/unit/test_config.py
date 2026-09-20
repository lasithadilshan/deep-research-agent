"""Unit tests for configuration and logging."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from deep_research.config import Settings, configure_logging, get_logger, mask_secrets
from deep_research.models.plan import ResearchMode


class TestSettings:
    def test_default_settings(self) -> None:
        settings = Settings()
        assert settings.gemini_model == "gemini-3.8-flash"
        assert settings.default_search_provider == "tavily"
        assert settings.default_research_mode == ResearchMode.STANDARD
        assert settings.max_budget_usd_per_run == 1.00
        assert settings.max_search_queries_per_iteration == 5
        assert settings.max_sources_per_query == 6
        assert settings.max_deep_research_iterations == 3
        assert settings.cache_enabled is True
        assert settings.cache_dir == Path(".deep_research/cache")
        assert settings.log_level == "INFO"

    def test_get_settings_singleton(self) -> None:
        from deep_research.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_custom_settings_override(self) -> None:
        settings = Settings(
            gemini_api_key="AIzaSyTestKey12345678901234567890",
            max_budget_usd_per_run=5.50,
            default_research_mode=ResearchMode.DEEP,
            log_level="debug",
        )
        assert settings.gemini_api_key == "AIzaSyTestKey12345678901234567890"
        assert settings.max_budget_usd_per_run == 5.50
        assert settings.default_research_mode == ResearchMode.DEEP
        assert settings.log_level == "DEBUG"

    def test_invalid_budget_raises(self) -> None:
        with pytest.raises(ValidationError):
            Settings(max_budget_usd_per_run=-2.0)

    def test_invalid_queries_per_iteration_raises(self) -> None:
        with pytest.raises(ValidationError):
            Settings(max_search_queries_per_iteration=0)


class TestSecretMasking:
    def test_mask_gemini_api_key_in_string(self) -> None:
        text = "Calling API with key AIzaSyD34db33f12345678901234567890123 now."
        masked = mask_secrets(text)
        assert "AIzaSy...[REDACTED]" in masked
        assert "AIzaSyD34db33f" not in masked

    def test_mask_tavily_api_key_in_string(self) -> None:
        text = "Tavily key is tvly-12345678901234567890123456789012"
        masked = mask_secrets(text)
        assert "tvly-...[REDACTED]" in masked
        assert "12345678901234567890" not in masked

    def test_mask_openai_and_anthropic_keys(self) -> None:
        oai = "sk-123456789012345678901234567890123456789012345678"
        ant = "sk-ant-123456789012345678901234567890123456789012345678"
        assert "sk-...[REDACTED]" in mask_secrets(oai)
        assert "sk-ant-...[REDACTED]" in mask_secrets(ant)

    def test_mask_sensitive_dict_keys(self) -> None:
        data = {
            "query": "quantum computing",
            "api_key": "supersecretkey999",
            "metadata": {
                "auth": "secret_token_abc",
                "nested_list": ["Bearer 123456789012345678901234", 42],
            },
        }
        masked = mask_secrets(data)
        assert masked["query"] == "quantum computing"
        assert "[REDACTED]" in masked["api_key"]
        assert "[REDACTED]" in masked["metadata"]["auth"]
        assert "Bearer [REDACTED]" in masked["metadata"]["nested_list"][0]
        assert masked["metadata"]["nested_list"][1] == 42


class TestLoggingConfiguration:
    def test_configure_logging_human_and_logger_binding(self) -> None:
        configure_logging(level="DEBUG", structured=False)
        logger = get_logger("TestModule")
        assert logger is not None

    def test_configure_logging_structured(self) -> None:
        configure_logging(level="INFO", structured=True)
        logger = get_logger()
        assert logger is not None

    def test_secret_masking_processor_direct(self) -> None:
        from deep_research.config.logging import secret_masking_processor

        event_dict = {
            "event": "query_dispatched",
            "api_key": "AIzaSySecretKey12345678901234567890",
            "normal_field": "public_data",
        }
        res = secret_masking_processor(None, "info", event_dict)
        assert "[REDACTED]" in str(res["api_key"])
        assert res["normal_field"] == "public_data"
