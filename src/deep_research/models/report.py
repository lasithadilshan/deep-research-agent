"""Final report, sections, and citation models."""

from datetime import datetime

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Audited citation linking an inline numeric marker to a primary source."""

    numeric_index: int = Field(ge=1, description="Sequential index e.g. 1 for [1]")
    source_id: str = Field(description="Points to Source.source_id")
    url: str = Field(description="Canonical URL of cited source")
    title: str = Field(description="Title of source document")
    author: str | None = Field(default=None, description="Author or organization")
    published_date: str | None = Field(default=None, description="Publication date string")
    accessed_date: str = Field(description="ISO date when document was retrieved")
    verbatim_quote_anchor: str = Field(
        description="Exact quote from source substantiating the citation"
    )

    def format_reference_entry(self) -> str:
        """Format bibliographic reference entry."""
        author_part = f"{self.author}, " if self.author else ""
        date_part = f" ({self.published_date})." if self.published_date else "."
        return (
            f'[{self.numeric_index}] {author_part}"{self.title}"{date_part} '
            f"Retrieved {self.accessed_date} from {self.url}"
        )


class Section(BaseModel):
    """Individual section of the final research report."""

    title: str = Field(description="Section heading")
    content: str = Field(description="Markdown content containing inline [N] citations")
    cited_numbers: list[int] = Field(
        default_factory=list, description="List of citation numbers referenced in this section"
    )


class ResearchReport(BaseModel):
    """Complete, fully cited research report."""

    title: str = Field(description="Report title")
    executive_summary: str = Field(description="High-level synthesis and key takeaways")
    sections: list[Section] = Field(default_factory=list)
    bibliography: list[Citation] = Field(default_factory=list)
    research_methodology: str = Field(
        default="", description="Methodology and search strategy notes"
    )
    known_limitations: list[str] = Field(
        default_factory=list,
        description="Identified data gaps, contradictions, or unverified claims",
    )
    total_sources_consulted: int = Field(ge=0, default=0)
    total_evidence_pieces: int = Field(ge=0, default=0)
    completed_at: datetime = Field(default_factory=datetime.utcnow)

    def to_markdown(self) -> str:
        """Render complete scientific report in standard Markdown."""
        lines = [
            f"# {self.title}\n",
            f"**Generated**: {self.completed_at.strftime('%Y-%m-%d %H:%M UTC')} | "
            f"**Sources Consulted**: {self.total_sources_consulted} | "
            f"**Evidence Items**: {self.total_evidence_pieces}\n",
            "## Executive Summary\n",
            f"{self.executive_summary}\n",
        ]

        for sec in self.sections:
            lines.append(f"## {sec.title}\n")
            lines.append(f"{sec.content}\n")

        if self.known_limitations:
            lines.append("## Research Limitations & Information Gaps\n")
            for lim in self.known_limitations:
                lines.append(f"- {lim}")
            lines.append("")

        if self.research_methodology:
            lines.append("## Methodology Notes\n")
            lines.append(f"{self.research_methodology}\n")

        lines.append("## References\n")
        # Ensure bibliography is sorted by numeric_index
        sorted_refs = sorted(self.bibliography, key=lambda c: c.numeric_index)
        for ref in sorted_refs:
            lines.append(ref.format_reference_entry())

        return "\n".join(lines)
