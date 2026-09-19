"""Search query representations and search provider response models."""

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Normalized search query specification dispatched to search providers."""

    query_text: str = Field(description="Search string or boolean query operators")
    sub_question_id: str | None = Field(
        default=None, description="Optional ID of the sub-question generating this query"
    )
    priority: int = Field(default=1, ge=1, le=5, description="Priority rank (1 highest)")
    target_domains: list[str] = Field(
        default_factory=list, description="Specific domains to limit search to (site: filter)"
    )
    excluded_domains: list[str] = Field(
        default_factory=list, description="Domains to exclude from results (-site: filter)"
    )


class SearchResult(BaseModel):
    """Normalized individual search hit from any provider."""

    title: str = Field(description="Title of search result")
    url: str = Field(description="Direct URL to page")
    snippet: str = Field(default="", description="Search snippet or summary")
    raw_score: float | None = Field(
        default=None, description="Relevance score returned by provider if available"
    )
    published_date: str | None = Field(
        default=None, description="Publication date string if detected by search engine"
    )
    direct_markdown: str | None = Field(
        default=None,
        description="Direct extracted markdown if provided by search engine (e.g. Tavily)",
    )


class SearchResponse(BaseModel):
    """Normalized output from a search provider query execution."""

    query: str = Field(description="Query executed")
    results: list[SearchResult] = Field(default_factory=list)
    provider_name: str = Field(description="Name of search provider executing query")
    execution_time_ms: float = Field(ge=0.0, default=0.0, description="Elapsed search latency")
    total_results_estimate: int | None = Field(
        default=None, description="Total matching results reported by engine"
    )
