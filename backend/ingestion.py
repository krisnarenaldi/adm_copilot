"""
IngestionPipeline — Fare Rules document ingestion for ADM Copilot.

Responsibilities:
  - ingest_document(file_path, airline_code) → None
    * Parse PDF with PyMuPDF (fitz); fall back to plain-text read for non-PDF
    * Validate airline_code is a non-empty string
    * Chunk text: 1000-char chunks with 100-char overlap
    * Store each chunk in ChromaDB collection "fare_rules" with metadata

Environment variables:
  - CHROMA_DB_PATH  Path for ChromaDB persistent storage (default: "./chroma_db")
"""

from __future__ import annotations

import logging
import os
from os.path import basename
import uuid
# Use a fixed namespace for deterministic chunk IDs
_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # UUID_NAMESPACE_DNS

import chromadb
from embedding import get_embedding_function

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking constants
# ---------------------------------------------------------------------------
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 100

# ---------------------------------------------------------------------------
# ChromaDB collection name
# ---------------------------------------------------------------------------
_COLLECTION_NAME = "fare_rules"

def _get_chroma_client() -> chromadb.PersistentClient:
    """Return a ChromaDB PersistentClient using the configured path."""
    chroma_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
    return chromadb.PersistentClient(path=chroma_path)


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """
    Split *text* into chunks of *chunk_size* characters with *overlap* characters
    of overlap between consecutive chunks.

    Properties guaranteed:
      - Every non-final chunk is exactly *chunk_size* characters long.
      - The first *overlap* characters of chunk i+1 equal the last *overlap*
        characters of chunk i.
      - The concatenation of all chunks (accounting for overlaps) reconstructs
        the original text without loss.
    """
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step

    return chunks


class IngestionPipeline:
    """Parses, chunks, and stores Fare Rules documents in ChromaDB."""

    def __init__(self, chroma_client: chromadb.PersistentClient | None = None) -> None:
        self._client = chroma_client or _get_chroma_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_document(self, file_path: str, airline_code: str) -> tuple[bool, str]:
        """
        Parse *file_path*, chunk the extracted text, and store chunks in
        ChromaDB with ``{"airline_code": airline_code}`` metadata.

        Args:
            file_path:    Absolute or relative path to a PDF or plain-text file.
            airline_code: Non-empty string identifying the airline (e.g. "GA").

        Returns:
            tuple (success: bool, message: str) — success=True if stored, False if duplicate or error
        """
        # 1. Validate airline_code
        if not isinstance(airline_code, str) or not airline_code.strip():
            logger.error(
                "ingest_document: invalid airline_code %r — document not stored.",
                airline_code,
            )
            return False, "Invalid airline code"

        airline_code = airline_code.strip()
        source = basename(file_path)

        # 2. Check if document already exists
        try:
            collection = self._client.get_or_create_collection(
                _COLLECTION_NAME,
                embedding_function=get_embedding_function()
            )
            existing = collection.get(
                where={"$and": [{"airline_code": airline_code}, {"source_file": source}]}
            )
            if len(existing["ids"]) > 0:
                logger.warning(
                    "ingest_document: document %r for airline %r already exists",
                    file_path,
                    airline_code,
                )
                return False, f"Document '{source}' for airline '{airline_code}' already uploaded"
        except Exception as exc:
            logger.warning(
                "ingest_document: failed to check for existing document, proceeding anyway — %s",
                exc,
            )

        # 3. Parse + chunk + store — wrapped so corrupt files don't halt the run
        try:
            text = self._extract_text(file_path)
            if not text:
                logger.warning(
                    "ingest_document: no text extracted from %r — skipping.",
                    file_path,
                )
                return False, "No text extracted from document"

            chunks = _chunk_text(text)
            if not chunks:
                logger.warning(
                    "ingest_document: chunking produced no chunks for %r — skipping.",
                    file_path,
                )
                return False, "Failed to extract document chunks"

            self._store_chunks(chunks, airline_code, file_path)
            logger.info(
                "ingest_document: stored %d chunks for airline %r from %r.",
                len(chunks),
                airline_code,
                file_path,
            )
            return True, f"Fare rules for {airline_code} ingested successfully"

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "ingest_document: failed to process %r — %s",
                file_path,
                exc,
                exc_info=True,
            )
            return False, f"Failed to process document: {exc}"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_text(self, file_path: str) -> str:
        """
        Extract raw text from *file_path*.

        Tries PyMuPDF first (handles PDF); falls back to plain-text read.
        Raises on I/O errors so the caller can log and skip.
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            pages: list[str] = []
            for page in doc:
                pages.append(page.get_text().rstrip("\n"))
            doc.close()
            text = "\n".join(pages)
            if text.strip():
                return text
            # PDF opened but yielded no text — fall through to plain-text read
        except Exception:  # noqa: BLE001
            # Not a valid PDF or fitz error — try plain text
            pass

        # Plain-text fallback
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def _store_chunks(
        self,
        chunks: list[str],
        airline_code: str,
        file_path: str,
    ) -> None:
        """Upsert *chunks* into the ChromaDB ``fare_rules`` collection."""
        collection = self._client.get_or_create_collection(
            _COLLECTION_NAME,
            embedding_function=get_embedding_function()
        )
        source = basename(file_path)

        # Deterministic IDs based on airline, source file, and chunk index
        ids = [
            str(uuid.uuid5(
                _NAMESPACE,
                f"{airline_code}:{source}:{i}"
            ))
            for i, _ in enumerate(chunks)
        ]
        metadatas = [
            {
                "airline_code": airline_code,
                "source_file": source,
                "chunk_index": i,
            }
            for i, _ in enumerate(chunks)
        ]

        collection.upsert(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )
