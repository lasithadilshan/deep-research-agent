"""Registry and factory for search providers."""

from collections.abc import Callable
from typing import Any

from deep_research.core.exceptions import ConfigurationError
from deep_research.providers.search.base import BaseSearchProvider

_SEARCH_PROVIDER_REGISTRY: dict[str, type[BaseSearchProvider]] = {}


def register_search_provider(
    name: str,
) -> Callable[[type[BaseSearchProvider]], type[BaseSearchProvider]]:
    """Decorator to register a search provider class under a normalized key."""

    def decorator(cls: type[BaseSearchProvider]) -> type[BaseSearchProvider]:
        key = name.strip().lower()
        _SEARCH_PROVIDER_REGISTRY[key] = cls
        return cls

    return decorator


def _ensure_builtins() -> None:
    """Ensure all default built-in providers are imported and registered."""
    if "arxiv" not in _SEARCH_PROVIDER_REGISTRY:
        import deep_research.providers.search.arxiv  # noqa: F401
    if "brave" not in _SEARCH_PROVIDER_REGISTRY:
        import deep_research.providers.search.brave  # noqa: F401
    if "duckduckgo" not in _SEARCH_PROVIDER_REGISTRY:
        import deep_research.providers.search.duckduckgo  # noqa: F401
    if "tavily" not in _SEARCH_PROVIDER_REGISTRY:
        import deep_research.providers.search.tavily  # noqa: F401
    if "mock" not in _SEARCH_PROVIDER_REGISTRY:
        import deep_research.providers.search.mock  # noqa: F401


def get_search_provider(name: str, **kwargs: Any) -> BaseSearchProvider:
    """Instantiate a registered search provider by name."""
    _ensure_builtins()
    key = name.strip().lower()
    if key not in _SEARCH_PROVIDER_REGISTRY:
        available = ", ".join(sorted(_SEARCH_PROVIDER_REGISTRY.keys()))
        raise ConfigurationError(
            f"Unknown search provider '{name}'. Available registered search providers: [{available}]"
        )
    provider_cls = _SEARCH_PROVIDER_REGISTRY[key]
    return provider_cls(**kwargs)


def list_search_providers() -> list[str]:
    """Return list of all registered search provider keys."""
    _ensure_builtins()
    return sorted(_SEARCH_PROVIDER_REGISTRY.keys())
