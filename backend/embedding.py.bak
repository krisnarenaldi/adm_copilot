
from typing import List, Optional
import chromadb
from chromadb.api.types import Documents, Embeddings, EmbeddingFunction
from sentence_transformers import SentenceTransformer


class SentenceTransformerEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self.model.encode(input, convert_to_numpy=True)
        return embeddings.tolist()


# Singleton instances for consistent use
_embedding_function: Optional[SentenceTransformerEmbeddingFunction] = None


def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    global _embedding_function
    if _embedding_function is None:
        _embedding_function = SentenceTransformerEmbeddingFunction()
    return _embedding_function

