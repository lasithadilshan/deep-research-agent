"""Configuration settings for AI Deep Research Agent."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from deep_research.models.plan import ResearchMode


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Primary LLM: Google Gemini ---
    gemini_api_key: str | None = Field(default=None, description="Google Gemini API key")
    gemini_model: str = Field(
        default="gemini-3.8-flash",
        description="Default Gemini model to use for planning, extraction, and synthesis",
    )

    # --- Optional Alternative LLMs ---
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key")
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for local Ollama instance",
    )

    # --- Search Providers ---
    default_search_provider: str = Field(
        default="tavily",
        description="Default search engine: 'tavily', 'google', 'brave', 'duckduckgo', or 'mock'",
    )
    tavily_api_key: str | None = Field(default=None, description="Tavily Search API key")
    google_cse_api_key: str | None = Field(default=None, description="Google Custom Search API key")
    google_cse_id: str | None = Field(default=None, description="Google Custom Search Engine ID")
    brave_search_api_key: str | None = Field(default=None, description="Brave Search API key")

    # --- Research Runtime Parameters ---
    default_research_mode: ResearchMode = Field(
        default=ResearchMode.STANDARD,
        description="Default execution depth: quick, standard, or deep",
    )
    max_search_queries_per_iteration: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max search queries dispatched in a single iteration",
    )
    max_sources_per_query: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Max results fetched per search query",
    )
    max_deep_research_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max iterations allowed in deep mode before forced termination",
    )

    # --- Cost & Resource Guardrails ---
    max_budget_usd_per_run: float = Field(
        default=1.00,
        gt=0.0,
        description="Hard spending ceiling in USD per research run",
    )
    request_timeout_seconds: int = Field(
        default=15,
        ge=5,
        le=120,
        description="Timeout for individual HTTP requests in seconds",
    )
    max_parallel_http_requests: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Max concurrent HTTP requests for web scraping",
    )

    # --- Storage & Caching ---
    cache_enabled: bool = Field(default=True, description="Enable disk caching for web & searches")
    cache_dir: Path = Field(
        default=Path(".deep_research/cache"),
        description="Directory path for persistent disk cache",
    )
    cache_expiration_hours: int = Field(
        default=72,
        ge=1,
        description="TTL for cached search queries and web pages",
    )

    # --- Observability ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    structured_logs: bool = Field(
        default=False,
        description="Output logs as structured JSON instead of human-readable text",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("cache_dir", mode="after")
    @classmethod
    def ensure_cache_dir_path(cls, v: Path) -> Path:
        return v.expanduser()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
