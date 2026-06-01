"""
VectorRetriever — Fare Rules chunk retrieval for ADM Copilot.

Responsibilities:
  - retrieve_chunks(airline_code, query_text, top_k=20) → list[Chunk]
    * Query ChromaDB "fare_rules" collection with airline_code metadata filter
    * Return up to top_k ranked Chunk objects
    * Return empty list when no chunks match (triggers 422 upstream)

Environment variables:
  - CHROMA_DB_PATH  Path for ChromaDB persistent storage (default: "./chroma_db")
"""

from __future__ import annotations

import logging
import os

import chromadb
from embedding import get_embedding_function

from models import Chunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ChromaDB collection name (must match IngestionPipeline)
# ---------------------------------------------------------------------------
_COLLECTION_NAME = "fare_rules"


def _get_chroma_client() -> chromadb.PersistentClient:
    """Return a ChromaDB PersistentClient using the configured path."""
    chroma_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
    return chromadb.PersistentClient(path=chroma_path)


class VectorRetriever:
    """Retrieves Fare Rules chunks from ChromaDB for a given airline."""

    def __init__(self, chroma_client: chromadb.PersistentClient | None = None) -> None:
        self._client = chroma_client or _get_chroma_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve_chunks(
        self,
        airline_code: str,
        query_text: str,
        top_k: int = 20,
    ) -> list[Chunk]:
        """
        Query ChromaDB for the *top_k* most relevant chunks for *airline_code*.

        Args:
            airline_code: Airline identifier used as a metadata filter (e.g. "GA").
            query_text:   The query string (ADM text) used for semantic search.
            top_k:        Maximum number of chunks to return (default 20).

        Returns:
            A list of up to *top_k* ``Chunk`` objects ordered by relevance
            (highest first).  Returns an empty list when the collection is
            empty or no chunks match the filter.
        """
        try:
            collection = self._client.get_or_create_collection(
                _COLLECTION_NAME,
                embedding_function=get_embedding_function()
            )

            # Guard: if the collection is empty there is nothing to query
            if collection.count() == 0:
                return []

            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where={"airline_code": airline_code},
            )

            documents: list[str] = results.get("documents", [[]])[0]
            metadatas: list[dict] = results.get("metadatas", [[]])[0]
            distances: list[float] = results.get("distances", [[]])[0]

            chunks: list[Chunk] = []
            for doc, meta, dist in zip(documents, metadatas, distances):
                chunks.append(
                    Chunk(
                        text=doc,
                        airline_code=meta.get("airline_code", airline_code),
                        relevance_score=1.0 - dist,
                    )
                )

            return chunks

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "retrieve_chunks: error querying ChromaDB for airline %r — %s",
                airline_code,
                exc,
                exc_info=True,
            )
            return []
