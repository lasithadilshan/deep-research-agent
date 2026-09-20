VENV ?= .venv
BIN = $(if $(wildcard $(VENV)/bin/*),$(VENV)/bin/,)

.PHONY: help install test coverage lint format typecheck check clean

help:
	@echo "AI Deep Research Agent - Developer Commands:"
	@echo "  make install    - Install package in editable mode with dev dependencies"
	@echo "  make test       - Run all offline unit & integration tests"
	@echo "  make coverage   - Run test suite with terminal coverage report"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Auto-format code using ruff"
	@echo "  make typecheck  - Run strict mypy type check"
	@echo "  make check      - Run all verification gates (format check, lint, typecheck, tests)"
	@echo "  make run-mock   - Run a test research inquiry locally using offline mock providers"
	@echo "  make clean      - Clean temporary files, caches, and test artifacts"

install:
	$(BIN)pip install -e ".[dev]"

test:
	$(BIN)pytest

coverage:
	$(BIN)pytest --cov=deep_research --cov-report=term-missing

lint:
	$(BIN)ruff check src tests

format:
	$(BIN)ruff format src tests

typecheck:
	$(BIN)mypy --strict src tests

check:
	$(BIN)ruff format --check src tests
	$(BIN)ruff check src tests
	$(BIN)mypy --strict src tests
	$(BIN)pytest

run-mock:
	$(BIN)deep-research run "Advancements in solid-state batteries" --llm mock --search mock --mode quick

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
