"""
retriever.py — Semantic retrieval from ChromaDB
------------------------------------------------
Queries the ecombot_kb collection using the same OpenAI embedding model
used during indexing (text-embedding-3-small).

Public API:
    retrieve(query, n_results)  — returns top matching chunks with metadata
"""

import logging
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
CHROMA_DIR = BASE_DIR / ".chromadb"
COLLECTION_NAME = "ecombot_kb"

load_dotenv(BASE_DIR / ".env")


def _get_collection():
    if not CHROMA_DIR.exists():
        raise RuntimeError(
            "ChromaDB index not found. Run embed_catalog.py first:\n"
            "  PYTHONPATH=. python3 rag/embed_catalog.py"
        )

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or OPENROUTER_API_KEY must be set in .env")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-small",
        ),
    )

MINIMUM_SCORE = 0.65  # chunks below this are too weak to ground an answer

def retrieve(query: str, n_results: int = 3) -> list[dict]:
    """
    Retrieve the top matching chunks from ecombot_kb for a given query.

    Args:
        query:     The user's question or search term.
        n_results: Number of chunks to return (default 3).

    Returns:
        List of dicts with keys: text, metadata, score.
        Returns empty list if collection is empty or retrieval fails.
    """
    if not query or not query.strip():
        return []

    try:
        collection = _get_collection()

        if collection.count() == 0:
            log.warning("ecombot_kb collection is empty. Run embed_catalog.py first.")
            return []

        results = collection.query(
            query_texts=[query.strip()],
            n_results=min(n_results, collection.count()),
        )

        chunks = _format(results)

        # Filter weak matches
        strong_chunks = [c for c in chunks if c["score"] >= 0.65]

        if not strong_chunks:
            log.info("No chunks above threshold for query: %s", query)

        return strong_chunks

    except Exception as exc:
        log.warning("Retrieval failed: %s", exc)
        return []


def _format(results: dict) -> list[dict]:
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    return [
        {
            "text": doc,
            "metadata": meta,
            "score": round(1 - dist, 4),
        }
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_queries = [
        "what is the warranty on the headphones?",
        "can I cancel my order?",
        "does the USB hub work with MacBook?",
    ]

    for q in test_queries:
        print(f"\nQuery: {q}")
        print("-" * 50)
        chunks = retrieve(q, n_results=2)
        if not chunks:
            print("No results.")
        for chunk in chunks:
            print(f"Score: {chunk['score']} | Type: {chunk['metadata'].get('chunk_type', 'faq')}")
            print(chunk["text"][:200])
            print()