"""PDF document parser extracting structured markdown and academic metadata."""

import io
import re
from dataclasses import dataclass, field
from typing import Any

from pypdf import PdfReader


@dataclass
class PDFDocument:
    """Parsed PDF document containing extracted text and academic metadata."""

    text: str
    title: str | None = None
    author: str | None = None
    page_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class PDFParser:
    """Extracts clean, normalized markdown text and metadata from PDF bytes."""

    def __init__(self, max_pages: int = 100) -> None:
        self.max_pages = max_pages

    def parse_bytes(self, pdf_bytes: bytes, max_pages: int | None = None) -> PDFDocument:
        """Parse raw PDF bytes into a structured PDFDocument.

        Extracts page-by-page text, cleans hyphenated words across line breaks,
        and retrieves document metadata if present.
        """
        if not pdf_bytes:
            return PDFDocument(text="", page_count=0)

        limit = max_pages or self.max_pages

        try:
            stream = io.BytesIO(pdf_bytes)
            reader = PdfReader(stream)

            if reader.is_encrypted:
                try:
                    # Attempt empty password decrypt
                    reader.decrypt("")
                except Exception:
                    return PDFDocument(
                        text="[Encrypted PDF Document - Decryption Required]",
                        page_count=len(reader.pages),
                    )

            total_pages = len(reader.pages)
            pages_to_process = min(total_pages, limit)

            # Metadata extraction
            doc_metadata: dict[str, Any] = {}
            title: str | None = None
            author: str | None = None

            if reader.metadata:
                for k, v in reader.metadata.items():
                    key_str = str(k).lstrip("/").lower()
                    if v:
                        doc_metadata[key_str] = str(v).strip()

                title = doc_metadata.get("title")
                author = doc_metadata.get("author")

            # Page-by-page text extraction
            page_blocks: list[str] = []
            for i in range(pages_to_process):
                page = reader.pages[i]
                page_text = page.extract_text() or ""
                cleaned_page_text = self._clean_page_text(page_text)
                if cleaned_page_text:
                    page_blocks.append(f"### Page {i + 1}\n\n{cleaned_page_text}")

            full_text = "\n\n".join(page_blocks)
            return PDFDocument(
                text=full_text,
                title=title,
                author=author,
                page_count=total_pages,
                metadata=doc_metadata,
            )
        except Exception as err:
            return PDFDocument(
                text=f"[Error parsing PDF content: {err}]",
                page_count=0,
            )

    def _clean_page_text(self, text: str) -> str:
        """Normalize whitespace, remove non-printable chars, and fix hyphenated wraps."""
        if not text:
            return ""

        # Remove null bytes and non-printable control characters
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

        # Fix hyphenated word breaks (e.g., 'supercon-\nductor' -> 'superconductor')
        cleaned = re.sub(r"(\b\w+)-\n(\w+\b)", r"\1\2", cleaned)

        # Normalize line breaks: turn lone newlines in paragraphs into spaces, preserve double newlines
        paragraphs = cleaned.split("\n\n")
        normalized_paragraphs: list[str] = []
        for p in paragraphs:
            # Replace single newlines within paragraph with space
            single_line_p = " ".join(line.strip() for line in p.split("\n") if line.strip())
            if single_line_p:
                normalized_paragraphs.append(single_line_p)

        return "\n\n".join(normalized_paragraphs)


def clean_pdf_to_markdown(pdf_bytes: bytes, max_pages: int = 100) -> str:
    """Convenience function extracting clean markdown text from PDF bytes."""
    parser = PDFParser(max_pages=max_pages)
    doc = parser.parse_bytes(pdf_bytes)
    return doc.text
