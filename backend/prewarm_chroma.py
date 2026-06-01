#!/usr/bin/env python3
"""
Quick script to pre-warm/download ChromaDB and cache the default embedding model!
"""

import chromadb


def main():
    print("Initializing ChromaDB to pre-warm the embedding model cache...")
    client = chromadb.Client()  # In-memory client just for initialization
    collection = client.create_collection("temp_warmup")
    collection.add(documents=["warmup"], ids=["1"])
    print("ChromaDB model cache is ready!")
    print("You can now safely start the ADM Copilot backend!")


if __name__ == "__main__":
    main()
