"""Unified exception hierarchy for AI Deep Research Agent."""


class DeepResearchError(Exception):
    """Base exception for all domain errors within deep research agent."""


class ConfigurationError(DeepResearchError):
    """Raised when environment or runtime settings are invalid or missing."""


class BudgetExceededError(DeepResearchError):
    """Raised when a research operation would breach the financial budget ceiling."""


class LLMProviderError(DeepResearchError):
    """Base exception for LLM provider failures."""


class LLMAuthenticationError(LLMProviderError):
    """Raised when LLM API credentials are invalid or missing."""


class LLMRateLimitError(LLMProviderError):
    """Raised when provider returns HTTP 429 or quota exhaustion."""


class LLMContextLengthExceededError(LLMProviderError):
    """Raised when prompt exceeds model maximum context window."""


class SearchProviderError(DeepResearchError):
    """Base exception for search provider failures."""


class WebFetchError(DeepResearchError):
    """Raised when HTTP web retrieval fails or is blocked."""


class CitationVerificationError(DeepResearchError):
    """Raised when citation or evidence grounding audit fails."""


class SessionNotFoundError(DeepResearchError):
    """Raised when a research session cannot be found or loaded from disk."""


class ResearchCancelledError(DeepResearchError):
    """Raised when research inquiry is cancelled by user during plan review."""
