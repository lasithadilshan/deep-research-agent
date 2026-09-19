"""Source modeling and credibility metadata structures."""

import hashlib
from datetime import datetime
from enum import StrEnum
from urllib.parse import parse_qsl, urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator


class SourceType(StrEnum):
    """Categorization of web sources."""

    ACADEMIC_PAPER = "academic_paper"
    GOVERNMENT_REPORT = "government_report"
    OFFICIAL_DOCUMENTATION = "official_documentation"
    NEWS_OUTLET = "news_outlet"
    CORPORATE_BLOG = "corporate_blog"
    COMMUNITY_FORUM = "community_forum"
    UNKNOWN = "unknown"


def canonicalize_url(raw_url: str) -> str:
    """Strip tracking query parameters and fragments to produce a canonical URL."""
    parsed = urlparse(raw_url.strip())
    # Tracking and session params to eliminate
    ignored_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "ref",
        "source",
        "ncid",
        "guccounter",
        "sr_share",
    }
    filtered_queries = [
        (k, val)
        for k, val in parse_qsl(parsed.query, keep_blank_values=False)
        if not k.startswith("utm_") and k.lower() not in ignored_params
    ]
    # Reassemble without fragment and with sorted filtered query parameters
    cleaned_query = "&".join(f"{k}={val}" for k, val in sorted(filtered_queries))
    # Normalize path: remove trailing slash if not root
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", cleaned_query, ""))


def generate_source_id(canonical_url: str) -> str:
    """Generate deterministic 12-char SHA-256 hash from canonical URL."""
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"src-{digest[:10]}"


class CredibilityMetadata(BaseModel):
    """Verifiable credibility indicators without fabricated subjective scores."""

    domain: str = Field(description="Host domain of the source")
    is_tld_verified: bool = Field(
        default=False,
        description="True for institutional TLDs (.gov, .edu, .mil) or curated research portals",
    )
    published_date: datetime | None = Field(default=None, description="ISO timestamp if extracted")
    has_author: bool = Field(default=False, description="True if author byline detected")
    is_https: bool = Field(default=True, description="True if retrieved over HTTPS")
    content_length_chars: int = Field(
        ge=0, default=0, description="Length of cleaned content in chars"
    )
    heuristic_trust_indicators: list[str] = Field(
        default_factory=list,
        description="List of verifiable facts e.g. ['peer_reviewed', 'reputable_wire_service']",
    )


class Source(BaseModel):
    """Ingested and cleaned research source."""

    source_id: str = Field(description="Deterministic ID derived from canonical URL")
    url: str = Field(description="Original requested URL")
    canonical_url: str = Field(description="Normalized canonical URL without tracking parameters")
    title: str = Field(default="", description="Extracted or retrieved document title")
    snippet: str = Field(default="", description="Search snippet or summary")
    source_type: SourceType = SourceType.UNKNOWN
    credibility: CredibilityMetadata
    cleaned_markdown: str = Field(
        default="",
        description="Boilerplate-free markdown content extracted from page",
    )
    token_count: int = Field(
        ge=0, default=0, description="Estimated token count of cleaned content"
    )
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("canonical_url", mode="before")
    @classmethod
    def clean_url(cls, v: str) -> str:
        return canonicalize_url(str(v))

    @classmethod
    def create(
        cls,
        url: str,
        title: str = "",
        snippet: str = "",
        source_type: SourceType = SourceType.UNKNOWN,
        cleaned_markdown: str = "",
        published_date: datetime | None = None,
        has_author: bool = False,
        trust_indicators: list[str] | None = None,
        token_count: int = 0,
    ) -> "Source":
        """Factory constructor ensuring deterministic source_id and credibility computation."""
        c_url = canonicalize_url(url)
        s_id = generate_source_id(c_url)
        domain = urlparse(c_url).netloc.lower()

        # Check for verified academic or institutional domains
        verified_tlds = {".gov", ".edu", ".mil", ".ac.uk", ".gov.uk"}
        verified_domains = {
            "arxiv.org",
            "nature.com",
            "ieee.org",
            "ncbi.nlm.nih.gov",
            "science.org",
        }
        is_verified = (
            any(domain.endswith(tld) for tld in verified_tlds) or domain in verified_domains
        )

        cred = CredibilityMetadata(
            domain=domain,
            is_tld_verified=is_verified,
            published_date=published_date,
            has_author=has_author,
            is_https=c_url.startswith("https://"),
            content_length_chars=len(cleaned_markdown),
            heuristic_trust_indicators=trust_indicators or [],
        )

        return cls(
            source_id=s_id,
            url=url,
            canonical_url=c_url,
            title=title,
            snippet=snippet,
            source_type=source_type,
            credibility=cred,
            cleaned_markdown=cleaned_markdown,
            token_count=token_count,
        )
