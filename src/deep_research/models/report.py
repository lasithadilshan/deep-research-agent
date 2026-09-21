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

    def to_json(self) -> str:
        """Export full structured report as formatted JSON."""
        return self.model_dump_json(indent=2)

    def to_html(self) -> str:
        """Render complete scientific report in styled, standalone HTML."""
        import html
        import re

        esc_title = html.escape(self.title)
        esc_summary = html.escape(self.executive_summary).replace("\n", "<br>")
        date_str = self.completed_at.strftime("%Y-%m-%d %H:%M UTC")

        def linkify_citations(text: str) -> str:
            escaped = html.escape(text)
            # Turn [1], [2] into clickable anchor links
            return re.sub(
                r"\[(\d+)\]",
                r'<a href="#ref-\1" class="citation-link">[\1]</a>',
                escaped,
            )

        sections_html = []
        for sec in self.sections:
            sec_title = html.escape(sec.title)
            sec_content = linkify_citations(sec.content).replace("\n\n", "</p><p>")
            sections_html.append(f"<section><h2>{sec_title}</h2><p>{sec_content}</p></section>")

        limitations_html = ""
        if self.known_limitations:
            lim_items = "".join(f"<li>{html.escape(lim)}</li>" for lim in self.known_limitations)
            limitations_html = (
                f'<div class="callout warning"><h3>Research Limitations & Information Gaps</h3>'
                f"<ul>{lim_items}</ul></div>"
            )

        methodology_html = ""
        if self.research_methodology:
            methodology_html = (
                f"<section><h2>Methodology Notes</h2>"
                f"<p>{html.escape(self.research_methodology)}</p></section>"
            )

        sorted_refs = sorted(self.bibliography, key=lambda c: c.numeric_index)
        refs_html = []
        for ref in sorted_refs:
            author_str = f"{html.escape(ref.author)}, " if ref.author else ""
            date_str_ref = f" ({html.escape(ref.published_date)})." if ref.published_date else "."
            safe_url = html.escape(ref.url)
            quote_str = (
                f'<span class="quote">“{html.escape(ref.verbatim_quote_anchor[:150])}…”</span>'
                if ref.verbatim_quote_anchor
                else ""
            )
            refs_html.append(
                f'<li id="ref-{ref.numeric_index}">'
                f'<strong>[{ref.numeric_index}]</strong> {author_str}<em>"{html.escape(ref.title)}"</em>{date_str_ref} '
                f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{safe_url}</a> '
                f"{quote_str}</li>"
            )

        bibliography_html = f"<ol class='bibliography'>{''.join(refs_html)}</ol>"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_title}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --border: #334155;
      --warning: #f59e0b;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.7;
      background: var(--bg);
      color: var(--text);
      max-width: 860px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
    }}
    h1 {{ color: #ffffff; font-size: 2.2rem; margin-bottom: 0.5rem; line-height: 1.2; }}
    .meta-bar {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
    .meta-badge {{
      display: inline-block;
      background: var(--card-bg);
      border: 1px solid var(--border);
      padding: 0.2rem 0.6rem;
      border-radius: 4px;
      margin-right: 0.5rem;
    }}
    h2 {{ color: var(--accent); font-size: 1.4rem; margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }}
    h3 {{ font-size: 1.1rem; color: #e2e8f0; margin-top: 1.2rem; }}
    p {{ margin-bottom: 1rem; color: #cbd5e1; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    a.citation-link {{
      font-weight: bold;
      color: var(--accent);
      padding: 0 0.15rem;
      font-size: 0.85em;
      vertical-align: super;
    }}
    .callout {{
      background: var(--card-bg);
      border-left: 4px solid var(--warning);
      padding: 1rem 1.25rem;
      border-radius: 0 6px 6px 0;
      margin: 1.5rem 0;
    }}
    .callout h3 {{ margin-top: 0; color: var(--warning); }}
    .callout ul {{ margin: 0; padding-left: 1.25rem; color: #cbd5e1; }}
    ol.bibliography {{ padding-left: 1.5rem; color: #cbd5e1; }}
    ol.bibliography li {{ margin-bottom: 0.75rem; font-size: 0.95rem; }}
    ol.bibliography li:target {{ background: rgba(56, 189, 248, 0.15); padding: 0.25rem; border-radius: 4px; }}
    .quote {{ display: block; font-size: 0.85rem; color: var(--muted); margin-top: 0.2rem; font-style: italic; }}
  </style>
</head>
<body>
  <header>
    <h1>{esc_title}</h1>
    <div class="meta-bar">
      <span class="meta-badge">📅 {date_str}</span>
      <span class="meta-badge">📚 {self.total_sources_consulted} Sources</span>
      <span class="meta-badge">🔍 {self.total_evidence_pieces} Evidence Points</span>
    </div>
  </header>
  <main>
    <section class="executive-summary">
      <h2>Executive Summary</h2>
      <p>{esc_summary}</p>
    </section>
    {"".join(sections_html)}
    {limitations_html}
    {methodology_html}
    <section>
      <h2>References & Audited Evidence</h2>
      {bibliography_html}
    </section>
  </main>
</body>
</html>"""
