"""Content cleaning and HTML-to-Markdown sanitization pipeline."""

import re
from typing import Any

import trafilatura
from bs4 import BeautifulSoup


def clean_html_to_markdown(raw_html: str, base_url: str = "") -> str:
    """Extract readable, boilerplate-free markdown from raw web HTML.

    Uses Trafilatura for article extraction with BeautifulSoup fallback.
    """
    if not raw_html or not raw_html.strip():
        return ""

    # Primary: Trafilatura readability & boilerplate removal
    extracted = trafilatura.extract(
        raw_html,
        url=base_url if base_url else None,
        output_format="markdown",
        include_links=True,
        include_images=False,
        favor_precision=True,
    )

    if extracted and len(extracted.strip()) > 100:
        return _normalize_markdown(extracted)

    # Fallback: BeautifulSoup targeted node stripping
    return _beautifulsoup_fallback_extract(raw_html)


def _beautifulsoup_fallback_extract(html: str) -> str:
    """Strip noise tags and extract text paragraphs cleanly."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content and noisy elements
    for element in soup.find_all(
        [
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
            "noscript",
            "svg",
            "iframe",
            "form",
            "button",
        ]
    ):
        element.decompose()

    # Extract headings and paragraphs
    blocks: list[str] = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = tag.get_text(separator=" ", strip=True)
        if text and len(text) > 20:
            if tag.name.startswith("h"):
                level = tag.name[1]
                blocks.append(f"{'#' * int(level)} {text}")
            elif tag.name == "li":
                blocks.append(f"- {text}")
            else:
                blocks.append(text)

    return _normalize_markdown("\n\n".join(blocks))


def _normalize_markdown(text: str) -> str:
    """Collapse excess whitespace and clean control characters."""
    # Remove null bytes and non-printable control characters
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Collapse 3+ newlines into 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def calculate_token_savings(raw_text: str, cleaned_text: str) -> dict[str, Any]:
    """Calculate token and character reduction metrics."""
    raw_chars = len(raw_text)
    clean_chars = len(cleaned_text)
    saved_chars = max(0, raw_chars - clean_chars)
    reduction_pct = (saved_chars / raw_chars * 100) if raw_chars > 0 else 0.0

    return {
        "raw_characters": raw_chars,
        "clean_characters": clean_chars,
        "reduction_percentage": round(reduction_pct, 2),
        "raw_token_estimate": max(1, raw_chars // 4),
        "clean_token_estimate": max(1, clean_chars // 4),
    }


def wrap_in_untrusted_boundary(content: str, source_id: str) -> str:
    """Isolate untrusted external text inside delimited safety XML boundaries.

    Escapes any internal closing tags to disarm prompt injection escape attempts.
    """
    safe_content = content.replace(
        "</untrusted_external_content>", "&lt;/untrusted_external_content&gt;"
    )
    return (
        f'<untrusted_external_content source_id="{source_id}">\n'
        f"{safe_content}\n"
        f"</untrusted_external_content>"
    )
