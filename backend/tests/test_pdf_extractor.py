"""
Unit tests for PDFExtractor.

Tests cover:
  - Valid PDF bytes → returns non-empty string
  - Empty bytes → returns ExtractionError
  - Corrupt/non-PDF bytes → returns ExtractionError
  - Multi-page PDF → text from all pages concatenated
  - Performance: extraction completes in under 500 ms
"""

from __future__ import annotations

import io
import time

import fitz  # PyMuPDF
import pytest

from models import ExtractionError
from pdf_extractor import PDFExtractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_bytes(pages: list[str]) -> bytes:
    """Create a minimal in-memory PDF with the given page texts."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPDFExtractor:
    def setup_method(self):
        self.extractor = PDFExtractor()

    # --- success cases ---

    def test_single_page_pdf_returns_text(self):
        pdf_bytes = _make_pdf_bytes(["Hello, ADM Copilot!"])
        result = self.extractor.extract_text(pdf_bytes)
        assert isinstance(result, str)
        assert "Hello, ADM Copilot!" in result

    def test_multi_page_pdf_returns_all_text(self):
        pdf_bytes = _make_pdf_bytes(["Page one content", "Page two content"])
        result = self.extractor.extract_text(pdf_bytes)
        assert isinstance(result, str)
        assert "Page one content" in result
        assert "Page two content" in result

    def test_returns_string_not_error_for_valid_pdf(self):
        pdf_bytes = _make_pdf_bytes(["Some fare rule text."])
        result = self.extractor.extract_text(pdf_bytes)
        assert not isinstance(result, ExtractionError)

    # --- error cases ---

    def test_empty_bytes_returns_extraction_error(self):
        result = self.extractor.extract_text(b"")
        assert isinstance(result, ExtractionError)

    def test_corrupt_bytes_returns_extraction_error(self):
        result = self.extractor.extract_text(b"this is not a pdf at all")
        assert isinstance(result, ExtractionError)

    def test_random_binary_returns_extraction_error(self):
        result = self.extractor.extract_text(bytes(range(256)) * 10)
        assert isinstance(result, ExtractionError)

    def test_extraction_error_has_message(self):
        result = self.extractor.extract_text(b"bad data")
        assert isinstance(result, ExtractionError)
        assert result.message  # non-empty message

    # --- performance ---

    def test_extraction_completes_under_500ms(self):
        """Requirement 5.4: extraction must complete in under 500 ms."""
        # Build a reasonably large PDF (10 pages of text)
        pages = [f"Page {i}: " + ("Fare rule content. " * 50) for i in range(10)]
        pdf_bytes = _make_pdf_bytes(pages)

        start = time.perf_counter()
        result = self.extractor.extract_text(pdf_bytes)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(result, str), "Expected successful extraction"
        assert elapsed_ms < 500, f"Extraction took {elapsed_ms:.1f} ms (limit: 500 ms)"
