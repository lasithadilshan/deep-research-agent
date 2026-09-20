"""Registry and factory for LLM providers."""

from collections.abc import Callable
from typing import Any

from deep_research.core.exceptions import ConfigurationError
from deep_research.providers.llm.base import BaseLLMProvider

_PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {}


def register_llm_provider(name: str) -> Callable[[type[BaseLLMProvider]], type[BaseLLMProvider]]:
    """Decorator to register an LLM provider class under a normalized key."""

    def decorator(cls: type[BaseLLMProvider]) -> type[BaseLLMProvider]:
        key = name.strip().lower()
        _PROVIDER_REGISTRY[key] = cls
        return cls

    return decorator


def get_llm_provider(name: str, **kwargs: Any) -> BaseLLMProvider:
    """Instantiate a registered LLM provider by name."""
    key = name.strip().lower()
    if key not in _PROVIDER_REGISTRY:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise ConfigurationError(
            f"Unknown LLM provider '{name}'. Available registered providers: [{available}]"
        )
    provider_cls = _PROVIDER_REGISTRY[key]
    return provider_cls(**kwargs)


def list_llm_providers() -> list[str]:
    """Return list of all registered LLM provider keys."""
    return sorted(_PROVIDER_REGISTRY.keys())
