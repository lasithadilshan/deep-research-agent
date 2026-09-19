# AI Deep Research Agent

> Production-grade, extensible open-source research engine powered by **Google Gemini 3.8 Flash**.

The **AI Deep Research Agent** takes complex, open-ended research questions, decomposes them into targeted sub-questions, systematically searches and ingests multiple sources, filters noise, extracts atomic evidence, and synthesizes cited research reports with strict numeric citations grounded in source passages.

## Key Features

- **Google Gemini 3.8 Flash First**: Ultra-fast, cost-effective reasoning with structured Pydantic schema enforcement.
- **Evidence-First Anti-Hallucination**: The report synthesizer only sees pre-extracted atomic evidence passages with verifiable verbatim quotes.
- **Strict Citation Verification**: Citation auditor verifies every single `[N]` reference against source content.
- **Double-Ended Provider Abstraction**: Easily plug in new Search engines (Tavily, Google, Brave, DuckDuckGo) and LLMs (Gemini, OpenAI, Anthropic, Ollama).
- **Cost & Token Guardrails**: Automatic HTML boilerplate stripping cuts tokens by ~85%; circuit-breaker budget enforcement.

## Quickstart

```bash
# Clone the repository
git clone https://github.com/your-org/deep-research-agent.git
cd deep-research-agent

# Set up virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Configure API keys
cp .env.example .env
# Edit .env with your GEMINI_API_KEY and TAVILY_API_KEY

# Run tests
pytest
```

## License

Apache 2.0
