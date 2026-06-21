"""
embed_catalog.py — Build ChromaDB vector store using OpenAI embeddings
-----------------------------------------------------------------------
Loads products.json and faq.json, splits each entry into focused chunks,
embeds them using OpenAI's text-embedding-3-small model, and upserts
everything into a single ChromaDB collection: ecombot_kb.

Run once to build, re-run anytime to refresh:
    cd ecombot/src
    PYTHONPATH=. python3 rag/embed_catalog.py
"""

import json
import logging
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.parent.parent      # ecombot/
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = BASE_DIR / ".chromadb"

PRODUCTS_FILE = DATA_DIR / "products.json"
FAQ_FILE = DATA_DIR / "faq.json"
COLLECTION_NAME = "ecombot_kb"

load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Embedding function (OpenAI)
# ---------------------------------------------------------------------------

def get_embedding_function():
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if openai_key:
        return OpenAIEmbeddingFunction(
            api_key=openai_key,
            model_name="text-embedding-3-small",
        )
    elif openrouter_key:
        return OpenAIEmbeddingFunction(
            api_key=openrouter_key,
            api_base="https://openrouter.ai/api/v1",
            model_name="openai/text-embedding-3-small",
        )
    else:
        raise RuntimeError("No OPENAI_API_KEY or OPENROUTER_API_KEY found in .env")


# ---------------------------------------------------------------------------
# Chunking — each product is split into focused sub-chunks
# ---------------------------------------------------------------------------

def chunk_product(product: dict) -> list[dict]:
    """
    Split one product into multiple focused chunks:
      1. Overview (name, category, price, description)
      2. Specs
      3. Shipping
      4. Warranty
      5. Support notes (if present)
    """
    pid = product["product_id"]
    name = product["name"]
    chunks = []

    # 1 — Overview
    chunks.append({
        "id": f"{pid}_overview",
        "text": (
            f"Product: {name} ({pid})\n"
            f"Category: {product.get('category', 'N/A')}\n"
            f"Price: ${product.get('price', 'N/A')}\n"
            f"Description: {product.get('description', '')}"
        ),
        "metadata": {"product_id": pid, "name": name, "chunk_type": "overview"},
    })

    # 2 — Specs
    specs = product.get("specs", {})
    if specs and specs.get("status") != "discontinued":
        spec_lines = "\n".join(f"  {k}: {v}" for k, v in specs.items())
        chunks.append({
            "id": f"{pid}_specs",
            "text": f"Product: {name} ({pid}) — Specifications\n{spec_lines}",
            "metadata": {"product_id": pid, "name": name, "chunk_type": "specs"},
        })

    # 3 — Shipping
    shipping = product.get("shipping")
    if shipping:
        chunks.append({
            "id": f"{pid}_shipping",
            "text": (
                f"Product: {name} ({pid}) — Shipping\n"
                f"Estimated delivery: {shipping.get('estimated_delivery_days')} business days\n"
                f"Free shipping eligible: {shipping.get('free_shipping_eligible')}\n"
                f"Weight: {shipping.get('weight_kg')}kg"
            ),
            "metadata": {"product_id": pid, "name": name, "chunk_type": "shipping"},
        })

    # 4 — Warranty
    warranty = product.get("warranty", {})
    if warranty and warranty.get("duration_months", 0) > 0:
        chunks.append({
            "id": f"{pid}_warranty",
            "text": (
                f"Product: {name} ({pid}) — Warranty\n"
                f"Duration: {warranty.get('duration_months')} months\n"
                f"Covers: {warranty.get('coverage')}\n"
                f"Does not cover: {warranty.get('excludes')}"
            ),
            "metadata": {"product_id": pid, "name": name, "chunk_type": "warranty"},
        })

    # 5 — Support notes
    support_notes = product.get("support_notes", "")
    if support_notes:
        chunks.append({
            "id": f"{pid}_support",
            "text": (
                f"Product: {name} ({pid}) — Troubleshooting & Support\n"
                f"{support_notes}"
            ),
            "metadata": {"product_id": pid, "name": name, "chunk_type": "support"},
        })

    return chunks


def chunk_faq(entry: dict) -> dict:
    """One FAQ entry = one chunk."""
    return {
        "id": entry["id"],
        "text": (
            f"FAQ — {entry.get('category', 'General')}\n"
            f"Q: {entry['question']}\n"
            f"A: {entry['answer']}"
        ),
        "metadata": {
            "faq_id": entry["id"],
            "category": entry.get("category", ""),
            "question": entry["question"],
            "chunk_type": "faq",
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_index() -> None:
    CHROMA_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_fn = get_embedding_function()

    # Delete and recreate collection for a clean refresh
    try:
        client.delete_collection(COLLECTION_NAME)
        log.info("Existing collection deleted — rebuilding fresh.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Load and chunk products
    with open(PRODUCTS_FILE) as f:
        products = json.load(f)

    product_chunks = []
    for product in products:
        product_chunks.extend(chunk_product(product))

    # Load and chunk FAQ
    with open(FAQ_FILE) as f:
        faq_entries = json.load(f)

    faq_chunks = [chunk_faq(entry) for entry in faq_entries]

    all_chunks = product_chunks + faq_chunks

    # Upsert into ChromaDB
    collection.add(
        ids=[c["id"] for c in all_chunks],
        documents=[c["text"] for c in all_chunks],
        metadatas=[c["metadata"] for c in all_chunks],
    )

    log.info(
        "Index built: %d product chunks + %d FAQ chunks = %d total → collection: %s",
        len(product_chunks),
        len(faq_chunks),
        len(all_chunks),
        COLLECTION_NAME,
    )
    log.info("ChromaDB stored at: %s", CHROMA_DIR)


if __name__ == "__main__":
    build_index()