"""Unit tests for PDF document parser and text extraction."""

import io

from pypdf import PdfWriter

from deep_research.tools.pdf_parser import PDFParser, clean_pdf_to_markdown


def test_pdf_parser_empty_bytes() -> None:
    parser = PDFParser()
    doc = parser.parse_bytes(b"")
    assert doc.text == ""
    assert doc.page_count == 0


def test_pdf_parser_corrupted_bytes() -> None:
    parser = PDFParser()
    doc = parser.parse_bytes(b"not a valid pdf header")
    assert "Error parsing PDF" in doc.text
    assert doc.page_count == 0


def test_pdf_parser_metadata_and_cleaning() -> None:
    parser = PDFParser()
    # Test text cleaner directly
    dirty_text = (
        "The room-temperature supercon-\nductor demonstrated zero resistance.\n\nParagraph 2."
    )
    cleaned = parser._clean_page_text(dirty_text)
    assert "superconductor" in cleaned
    assert "Paragraph 2." in cleaned


def test_pdf_parser_convenience_function() -> None:
    # Test with empty bytes
    result = clean_pdf_to_markdown(b"")
    assert result == ""


def test_pdf_parser_metadata_and_structure() -> None:
    writer = PdfWriter()
    writer.add_metadata({"/Title": "Quantum Error Correction", "/Author": "Dr. Smith"})
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    pdf_bytes = stream.getvalue()

    parser = PDFParser(max_pages=10)
    doc = parser.parse_bytes(pdf_bytes)
    assert doc.title == "Quantum Error Correction"
    assert doc.author == "Dr. Smith"
    assert doc.page_count == 2
