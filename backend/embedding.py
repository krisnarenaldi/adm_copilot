
import os
from typing import List, Optional
import chromadb
from chromadb.api.types import Documents, Embeddings, EmbeddingFunction
from openai import OpenAI


class OpenAIEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model_name: str = "text-embedding-3-small"):
        # Resolve API key & base URL: LLMLITE_KEY > OPENAI_API_KEY > None (let OpenAI() use its own default)
        api_key = os.environ.get("LLMLITE_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("LLMLITE_BASE_URL")
        
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
            
        self.client = OpenAI(**kwargs)
        self.model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        # OpenAI embedding API expects a list of strings
        response = self.client.embeddings.create(
            model=self.model_name,
            input=input
        )
        # Sort by index to preserve order, then extract embeddings
        embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        return embeddings


# Singleton instances for consistent use
_embedding_function: Optional[OpenAIEmbeddingFunction] = None


def get_embedding_function() -> OpenAIEmbeddingFunction:
    global _embedding_function
    if _embedding_function is None:
        _embedding_function = OpenAIEmbeddingFunction()
    return _embedding_function

