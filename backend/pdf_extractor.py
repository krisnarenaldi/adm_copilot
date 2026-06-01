"""
PDFExtractor — extracts raw text from PDF bytes using PyMuPDF (fitz).

Design requirements:
  - Accept raw PDF bytes (not a file path).
  - Use fitz.open(stream=..., filetype="pdf") to open from memory.
  - Extract text from all pages and concatenate.
  - Return the extracted text as a str on success.
  - Return an ExtractionError (not raise) on any failure.
  - Must complete in under 500 ms (bytes-in-memory → text-returned).
"""

from __future__ import annotations

import fitz  # PyMuPDF

from models import ExtractionError


class PDFExtractor:
    """Extracts plain text from a PDF supplied as raw bytes."""

    def extract_text(self, pdf_bytes: bytes) -> str | ExtractionError:
        """
        Extract all text from *pdf_bytes* and return it as a single string.

        Parameters
        ----------
        pdf_bytes:
            Raw bytes of a PDF file (e.g. the body of an uploaded file).

        Returns
        -------
        str
            Concatenated text from every page, separated by newlines.
        ExtractionError
            If the bytes cannot be opened as a PDF, if the document is
            encrypted/corrupt, or if any other extraction failure occurs.
        """
        if not pdf_bytes:
            return ExtractionError("PDF bytes are empty.")

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:  # fitz.FileDataError, RuntimeError, etc.
            return ExtractionError(
                f"Failed to open PDF: {exc}"
            )

        try:
            if doc.is_encrypted:
                return ExtractionError(
                    "PDF is encrypted and cannot be extracted without a password."
                )

            pages_text: list[str] = []
            for page in doc:
                try:
                    pages_text.append(page.get_text())
                except Exception as exc:
                    return ExtractionError(
                        f"Failed to extract text from page {page.number}: {exc}"
                    )

            return "\n".join(pages_text)

        finally:
            doc.close()
