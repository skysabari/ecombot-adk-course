"""
pdf_chunker.py — Extract and chunk text from the ecombot knowledge base PDF
----------------------------------------------------------------------------
Implements section-aware chunking with overlap so that:
  - Related content stays together (product info, shipping rules, FAQ pairs)
  - Context is not lost at chunk boundaries via overlap
  - FAQ Q&A pairs are never split across chunks

Chunk strategy:
  1. Extract text page by page using pdfplumber
  2. Detect section/sub-section headings to create natural boundaries
  3. Build chunks of ~500 chars with ~100 char overlap
  4. Clean up PDF artifacts like (cid:127) bullet markers

Usage:
    cd ecombot/src
    PYTHONPATH=. python3 rag/pdf_chunker.py
"""

import re
import logging
from pathlib import Path

import pdfplumber

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
PDF_PATH = BASE_DIR / "data" / "ecombot_knowledge_base.pdf"

CHUNK_SIZE    = 500   # target characters per chunk
CHUNK_OVERLAP = 100   # overlap characters between consecutive chunks

# Known section and sub-section headings in the PDF
KNOWN_HEADINGS = {
    # Top-level sections
    "1. Product Catalogue", "2. Shipping Policy", "3. Returns and Refunds",
    "4. Warranty Terms", "5. Frequently Asked Questions",
    "6. Support Contact Information", "Table of Contents",
    # Sub-headings
    "Standard Delivery", "Free Shipping", "Express Shipping", "Tracking",
    "International Shipping", "Return Eligibility", "How to Initiate a Return",
    "Defective Items", "Refund Processing", "Non-Returnable Items",
    "Coverage Summary", "Making a Warranty Claim", "Warranty Exclusions",
    "Orders", "Products", "Payments", "How to Reach Us", "Escalation",
}


# ---------------------------------------------------------------------------
# Step 1 — Extract raw text from PDF
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: Path) -> list[dict]:
    """Extract text from each page as a list of {'page': int, 'text': str}."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                cleaned = _clean(text)
                pages.append({"page": i, "text": cleaned})
    log.info("Extracted text from %d pages.", len(pages))
    return pages


def _clean(text: str) -> str:
    """Remove PDF artifacts and normalise whitespace."""
    # Replace (cid:127) bullet markers with a dash
    text = re.sub(r"\(cid:\d+\)", "- ", text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Step 2 — Split into sections using known headings
# ---------------------------------------------------------------------------

def split_into_sections(pages: list[dict]) -> list[dict]:
    """
    Join all page text then split into logical sections.
    Uses KNOWN_HEADINGS for reliable boundary detection.
    """
    sections = []
    current_title = "Cover"
    current_text  = []
    current_page  = 1

    for page in pages:
        # Skip cover and TOC pages
        if page["page"] <= 2:
            continue

        lines = page["text"].split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if _is_heading(line):
                if current_text:
                    sections.append({
                        "title": current_title,
                        "text":  " ".join(current_text).strip(),
                        "page":  current_page,
                    })
                current_title = line
                current_text  = []
                current_page  = page["page"]
            else:
                current_text.append(line)

    # Flush last section
    if current_text:
        sections.append({
            "title": current_title,
            "text":  " ".join(current_text).strip(),
            "page":  current_page,
        })

    # Filter out empty or very short sections (e.g. TOC entries)
    sections = [s for s in sections if len(s["text"]) > 30]

    log.info("Detected %d sections.", len(sections))
    return sections


def _is_heading(line: str) -> bool:
    """Return True if line is a known heading or numbered section."""
    if line in KNOWN_HEADINGS:
        return True
    # Numbered top-level: "1. Product Catalogue"
    if re.match(r"^\d+\.\s+[A-Z]", line):
        return True
    # Product lines: "Wireless Noise-Cancelling Headphones (PRD-101)"
    if re.search(r"\(PRD-\d+\)$", line):
        return True
    return False


# ---------------------------------------------------------------------------
# Step 3 — Chunk sections with overlap
# ---------------------------------------------------------------------------

def chunk_section(section: dict) -> list[dict]:
    """
    Split one section into overlapping chunks of ~CHUNK_SIZE characters.
    Short sections become a single chunk.
    Q&A pairs are protected from being split.
    """
    text  = _protect_qa_pairs(section["text"])
    title = section["title"]
    page  = section["page"]

    if len(text) <= CHUNK_SIZE:
        return [{
            "id":          _make_id(title, 0),
            "text":        f"{title}\n{text}",
            "title":       title,
            "page":        page,
            "chunk_index": 0,
        }]

    chunks = []
    start  = 0
    index  = 0

    while start < len(text):
        end = start + CHUNK_SIZE

        if end >= len(text):
            chunk_text = text[start:]
        else:
            end = _find_break(text, end)
            chunk_text = text[start:end]

        chunks.append({
            "id":          _make_id(title, index),
            "text":        f"{title}\n{chunk_text.strip()}",
            "title":       title,
            "page":        page,
            "chunk_index": index,
        })

        start  = end - CHUNK_OVERLAP
        index += 1

        if start >= len(text):
            break

    return chunks


def _find_break(text: str, pos: int) -> int:
    """Find the nearest clean break (sentence end or whitespace) near pos."""
    window = text[max(0, pos - 100): pos + 1]
    for punct in (".", "!", "?", "\n"):
        idx = window.rfind(punct)
        if idx != -1:
            return max(0, pos - 100) + idx + 1
    idx = text.rfind(" ", max(0, pos - 50), pos)
    return idx if idx != -1 else pos


def _protect_qa_pairs(text: str) -> str:
    """Join Q: and A: so they are never split across chunk boundaries."""
    return re.sub(r"(Q:\s.+?)\n(A:\s)", r"\1 \2", text)


def _make_id(title: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"{slug}_{index}"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def extract_and_chunk(pdf_path: Path = PDF_PATH) -> list[dict]:
    """
    Full pipeline: extract → section split → chunk with overlap.
    Returns a list of chunk dicts ready for embedding.
    """
    pages    = extract_pages(pdf_path)
    sections = split_into_sections(pages)
    chunks   = []

    for section in sections:
        chunks.extend(chunk_section(section))

    log.info(
        "Final: %d chunks from %d sections  (size~%d chars, overlap~%d chars).",
        len(chunks), len(sections), CHUNK_SIZE, CHUNK_OVERLAP,
    )
    return chunks


# ---------------------------------------------------------------------------
# Preview — run directly to inspect before embedding
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    chunks = extract_and_chunk()

    print(f"\nTotal chunks: {len(chunks)}\n{'=' * 60}")
    for chunk in chunks:
        print(f"\n[{chunk['id']}]  page {chunk['page']}  chunk #{chunk['chunk_index']}")
        print(f"Length: {len(chunk['text'])} chars")
        print("-" * 60)
        print(chunk["text"][:300])
        if len(chunk["text"]) > 300:
            print("  ...")
        print()


# ---------------------------------------------------------------------------
# Metadata builder
# ---------------------------------------------------------------------------

DOCUMENT_TITLE = "Ecombot Customer Support Knowledge Base"
SOURCE_FILE    = "ecombot_knowledge_base.pdf"
DOC_TYPE       = "pdf"

# Map section titles to human-readable section names
SECTION_MAP = {
    "1. Product Catalogue":           "Product Catalogue",
    "2. Shipping Policy":             "Shipping Policy",
    "3. Returns and Refunds":         "Returns and Refunds",
    "4. Warranty Terms":              "Warranty Terms",
    "5. Frequently Asked Questions":  "FAQ",
    "6. Support Contact Information": "Support Contact",
    "Standard Delivery":              "Shipping Policy",
    "Free Shipping":                  "Shipping Policy",
    "Express Shipping":               "Shipping Policy",
    "Tracking":                       "Shipping Policy",
    "International Shipping":         "Shipping Policy",
    "Return Eligibility":             "Returns and Refunds",
    "How to Initiate a Return":       "Returns and Refunds",
    "Defective Items":                "Returns and Refunds",
    "Refund Processing":              "Returns and Refunds",
    "Non-Returnable Items":           "Returns and Refunds",
    "Coverage Summary":               "Warranty Terms",
    "Making a Warranty Claim":        "Warranty Terms",
    "Warranty Exclusions":            "Warranty Terms",
    "Orders":                         "FAQ",
    "Products":                       "FAQ",
    "Payments":                       "FAQ",
    "How to Reach Us":                "Support Contact",
    "Escalation":                     "Support Contact",
}


def build_metadata(chunk: dict) -> dict:
    """
    Build a metadata dict for a chunk.
    Every chunk gets: source_file, document_title, section,
    sub_section, page, doc_type, chunk_index.
    """
    title = chunk["title"]

    # Detect product ID if this is a product chunk
    product_id = None
    match = re.search(r"PRD-\d+", title)
    if match:
        product_id = match.group()

    metadata = {
        "source_file":     SOURCE_FILE,
        "document_title":  DOCUMENT_TITLE,
        "section":         SECTION_MAP.get(title, title),
        "sub_section":     title,
        "page":            chunk["page"],
        "doc_type":        DOC_TYPE,
        "chunk_index":     chunk["chunk_index"],
    }

    if product_id:
        metadata["product_id"] = product_id

    return metadata


def extract_and_chunk_with_metadata(pdf_path: Path = PDF_PATH) -> list[dict]:
    """
    Full pipeline with metadata attached to every chunk.
    Returns list of dicts: {id, text, title, page, chunk_index, metadata}
    """
    chunks = extract_and_chunk(pdf_path)
    for chunk in chunks:
        chunk["metadata"] = build_metadata(chunk)
    log.info("Metadata attached to all %d chunks.", len(chunks))
    return chunks


if __name__ == "__main__":
    chunks = extract_and_chunk_with_metadata()

    print(f"\nTotal chunks: {len(chunks)}\n{'=' * 60}")
    for chunk in chunks:
        print(f"\n[{chunk['id']}]")
        print(f"  section     : {chunk['metadata']['section']}")
        print(f"  sub_section : {chunk['metadata']['sub_section']}")
        print(f"  page        : {chunk['metadata']['page']}")
        print(f"  doc_type    : {chunk['metadata']['doc_type']}")
        print(f"  source_file : {chunk['metadata']['source_file']}")
        if chunk['metadata'].get('product_id'):
            print(f"  product_id  : {chunk['metadata']['product_id']}")
        print(f"  text preview: {chunk['text'][:120]}...")