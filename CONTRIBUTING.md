# Contributing to AI Deep Research Agent

Thank you for your interest in contributing to **AI Deep Research Agent**! This document provides guidelines for contributing code, reporting bugs, suggesting features, and extending providers.

---

## Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone. Please treat contributors with respect and professionalism.

---

## Development Setup

The project requires **Python 3.11** or **3.12** and recommends using `uv` for fast dependency management.

```bash
# 1. Fork and clone the repository
git clone https://github.com/<your-username>/deep-research-agent.git
cd deep-research-agent

# 2. Create and activate a virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install in editable mode with development dependencies
uv pip install -e ".[dev]"

# 4. Set up your environment variables
cp .env.example .env
# Fill in your GEMINI_API_KEY (optional for mock tests)
```

---

## Development Workflow & Standards

### 1. Strict Typing (`mypy --strict`)
All code must pass `mypy --strict` with zero errors. Do not use untyped functions or unannotated arguments.

```bash
mypy --strict src tests
```

### 2. Linting & Code Formatting (`ruff`)
We use `ruff` for both linting and formatting. Line length is 100 characters.

```bash
# Check formatting
ruff format --check src tests

# Format files
ruff format src tests

# Lint checks
ruff check src tests
```

### 3. Comprehensive Offline Tests (`pytest`)
All tests must execute offline without external network dependencies. Use `MockLLMProvider` and `MockSearchProvider` for testing agents and workflows.

```bash
pytest --cov=deep_research --cov-report=term-missing
```

---

## Extending the Agent System

### Adding a New Search Provider

1. Create a new module in `src/deep_research/providers/search/<provider_name>.py`.
2. Inherit from `BaseSearchProvider` and register with `@register_search_provider("<provider_name>")`.
3. Implement `search(self, query: str, max_results: int = 10, **kwargs) -> SearchResponse`.
4. Export the provider in `src/deep_research/providers/search/__init__.py`.
5. Add unit tests in `tests/unit/test_providers_search.py`.

### Adding a New LLM Provider

1. Create a new module in `src/deep_research/providers/llm/<provider_name>.py`.
2. Inherit from `BaseLLMProvider` and register with `@register_llm_provider("<provider_name>")`.
3. Implement `generate_text` and `generate_structured(..., response_model: type[T]) -> tuple[T, TokenUsage]`.
4. Export the provider in `src/deep_research/providers/llm/__init__.py`.
5. Add unit tests in `tests/unit/test_providers_llm.py`.

---

## Pull Request Guidelines

1. **Branch Naming**: Use descriptive branches like `feat/brave-search`, `fix/quote-grounding`, or `docs/update-architecture`.
2. **Commit Messages**: Follow Conventional Commits format:
   - `feat(...)`: New feature or agent capability
   - `fix(...)`: Bug fix
   - `test(...)`: Test suite improvements
   - `docs(...)`: Documentation updates
   - `ci(...)`: GitHub Actions or build changes
3. Ensure all tests, mypy, and ruff checks pass locally before opening a PR:
   ```bash
   make check  # or pytest && mypy --strict src tests && ruff check src tests
   ```
