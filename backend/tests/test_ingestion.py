"""
Unit tests for IngestionPipeline and VectorRetriever.

Tests cover:
  IngestionPipeline._chunk_text:
    - empty string → []
    - text ≤ 1000 chars → single chunk equal to text
    - text > 1000 chars → multiple chunks, each non-final exactly 1000 chars
    - overlap: first 100 chars of chunk i+1 == last 100 chars of chunk i
    - reconstruction: original text recoverable from chunks

  IngestionPipeline.ingest_document:
    - empty airline_code → no store, logs error
    - whitespace-only airline_code → no store, logs error
    - non-string airline_code → no store, logs error
    - corrupt/unparseable file → logs error, does not raise
    - valid PDF-like text file → chunks stored with correct metadata

  VectorRetriever.retrieve_chunks:
    - empty collection → returns []
    - results mapped to Chunk objects with correct fields
    - exception in query → returns []
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from ingestion import IngestionPipeline, _chunk_text
from models import Chunk


# ---------------------------------------------------------------------------
# _chunk_text — pure function tests
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_empty_string_returns_empty_list(self):
        assert _chunk_text("") == []

    def test_short_text_returns_single_chunk(self):
        text = "Hello, world!"
        chunks = _chunk_text(text)
        assert chunks == [text]

    def test_exactly_1000_chars_returns_single_chunk(self):
        text = "x" * 1000
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_1001_chars_returns_two_chunks(self):
        text = "a" * 1001
        chunks = _chunk_text(text)
        assert len(chunks) == 2

    def test_non_final_chunks_are_exactly_1000_chars(self):
        text = "z" * 3500
        chunks = _chunk_text(text)
        for chunk in chunks[:-1]:
            assert len(chunk) == 1000

    def test_overlap_between_consecutive_chunks(self):
        # Use a text long enough to produce at least 2 chunks
        text = "".join(str(i % 10) for i in range(2000))
        chunks = _chunk_text(text)
        assert len(chunks) >= 2
        for i in range(len(chunks) - 1):
            # Last 100 chars of chunk i == first 100 chars of chunk i+1
            assert chunks[i][-100:] == chunks[i + 1][:100]

    def test_reconstruction_from_chunks(self):
        """Concatenating chunks with overlap removed reconstructs the original."""
        text = "abcdefghij" * 200  # 2000 chars
        chunks = _chunk_text(text)
        # Reconstruct: first chunk in full, then each subsequent chunk minus the overlap
        reconstructed = chunks[0]
        for chunk in chunks[1:]:
            reconstructed += chunk[100:]
        assert reconstructed == text

    def test_single_char_text(self):
        chunks = _chunk_text("X")
        assert chunks == ["X"]

    def test_custom_chunk_size_and_overlap(self):
        text = "a" * 50
        chunks = _chunk_text(text, chunk_size=20, overlap=5)
        # step = 20 - 5 = 15
        # starts: 0, 15, 30 — loop breaks at start=30 because end=50 >= len(text)=50
        assert len(chunks) == 3
        assert chunks[0] == "a" * 20
        assert chunks[1] == "a" * 20
        # overlap check
        assert chunks[0][-5:] == chunks[1][:5]


# ---------------------------------------------------------------------------
# IngestionPipeline.ingest_document — validation tests
# ---------------------------------------------------------------------------

def _make_pipeline_with_mock_client() -> tuple[IngestionPipeline, MagicMock]:
    """Return a pipeline wired to a mock ChromaDB client."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    pipeline = IngestionPipeline(chroma_client=mock_client)
    return pipeline, mock_collection


class TestIngestionPipelineValidation:
    def test_empty_airline_code_does_not_store(self):
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("Some fare rules text.")
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, "")
        finally:
            os.unlink(tmp_path)
        mock_collection.upsert.assert_not_called()

    def test_whitespace_only_airline_code_does_not_store(self):
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("Some fare rules text.")
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, "   ")
        finally:
            os.unlink(tmp_path)
        mock_collection.upsert.assert_not_called()

    def test_none_airline_code_does_not_store(self):
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("Some fare rules text.")
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, None)  # type: ignore[arg-type]
        finally:
            os.unlink(tmp_path)
        mock_collection.upsert.assert_not_called()

    def test_corrupt_file_does_not_raise(self):
        """A corrupt/unparseable file must be skipped without raising."""
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        # Pass a path that doesn't exist — _extract_text will raise, which
        # ingest_document must catch and log.
        pipeline.ingest_document("/nonexistent/path/file.pdf", "GA")
        mock_collection.upsert.assert_not_called()

    def test_valid_text_file_stores_chunks(self):
        """A valid plain-text file with >1000 chars stores multiple chunks."""
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        content = "Fare rule content. " * 100  # ~1900 chars
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(content)
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, "GA")
        finally:
            os.unlink(tmp_path)

        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args
        documents = call_kwargs[1].get("documents") or call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs.get("documents")
        # Retrieve via keyword args
        kwargs = mock_collection.upsert.call_args.kwargs
        assert len(kwargs["documents"]) >= 2
        assert len(kwargs["ids"]) == len(kwargs["documents"])
        assert len(kwargs["metadatas"]) == len(kwargs["documents"])

    def test_metadata_contains_airline_code(self):
        """Every stored chunk must have airline_code in its metadata."""
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        content = "x" * 2000
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(content)
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, "SQ")
        finally:
            os.unlink(tmp_path)

        kwargs = mock_collection.upsert.call_args.kwargs
        for meta in kwargs["metadatas"]:
            assert meta["airline_code"] == "SQ"

    def test_metadata_contains_source_file_and_chunk_index(self):
        """Metadata must include source_file (basename) and chunk_index."""
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        content = "y" * 1500
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(content)
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, "GA")
        finally:
            os.unlink(tmp_path)

        kwargs = mock_collection.upsert.call_args.kwargs
        for i, meta in enumerate(kwargs["metadatas"]):
            assert "source_file" in meta
            assert meta["chunk_index"] == i

    def test_short_text_stores_single_chunk(self):
        """A file with ≤1000 chars produces exactly one chunk."""
        pipeline, mock_collection = _make_pipeline_with_mock_client()
        content = "Short fare rule."
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(content)
            tmp_path = f.name
        try:
            pipeline.ingest_document(tmp_path, "GA")
        finally:
            os.unlink(tmp_path)

        kwargs = mock_collection.upsert.call_args.kwargs
        assert len(kwargs["documents"]) == 1
        assert kwargs["documents"][0] == content


# ---------------------------------------------------------------------------
# VectorRetriever.retrieve_chunks
# ---------------------------------------------------------------------------

class TestVectorRetriever:
    def _make_retriever(self, collection_count: int = 0, query_results: dict | None = None):
        from retriever import VectorRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = collection_count

        if query_results is not None:
            mock_collection.query.return_value = query_results

        mock_client.get_or_create_collection.return_value = mock_collection
        retriever = VectorRetriever(chroma_client=mock_client)
        return retriever, mock_collection

    def test_empty_collection_returns_empty_list(self):
        retriever, _ = self._make_retriever(collection_count=0)
        result = retriever.retrieve_chunks("GA", "some query")
        assert result == []

    def test_results_mapped_to_chunk_objects(self):
        query_results = {
            "documents": [["Chunk text one", "Chunk text two"]],
            "metadatas": [[{"airline_code": "GA"}, {"airline_code": "GA"}]],
            "distances": [[0.1, 0.3]],
        }
        retriever, _ = self._make_retriever(collection_count=2, query_results=query_results)
        chunks = retriever.retrieve_chunks("GA", "query")

        assert len(chunks) == 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert chunks[0].text == "Chunk text one"
        assert chunks[0].airline_code == "GA"
        assert abs(chunks[0].relevance_score - 0.9) < 1e-9
        assert chunks[1].text == "Chunk text two"
        assert abs(chunks[1].relevance_score - 0.7) < 1e-9

    def test_exception_in_query_returns_empty_list(self):
        from retriever import VectorRetriever

        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.side_effect = RuntimeError("ChromaDB error")
        mock_client.get_or_create_collection.return_value = mock_collection

        retriever = VectorRetriever(chroma_client=mock_client)
        result = retriever.retrieve_chunks("GA", "query")
        assert result == []

    def test_query_uses_airline_code_filter(self):
        query_results = {
            "documents": [["Some text"]],
            "metadatas": [[{"airline_code": "SQ"}]],
            "distances": [[0.2]],
        }
        retriever, mock_collection = self._make_retriever(
            collection_count=1, query_results=query_results
        )
        retriever.retrieve_chunks("SQ", "query text", top_k=10)

        call_kwargs = mock_collection.query.call_args.kwargs
        assert call_kwargs["where"] == {"airline_code": "SQ"}
        assert call_kwargs["n_results"] == 10

    def test_default_top_k_is_20(self):
        query_results = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        retriever, mock_collection = self._make_retriever(
            collection_count=1, query_results=query_results
        )
        retriever.retrieve_chunks("GA", "query")

        call_kwargs = mock_collection.query.call_args.kwargs
        assert call_kwargs["n_results"] == 20
