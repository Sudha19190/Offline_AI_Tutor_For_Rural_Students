"""
core/ingest.py - Ingestion pipeline for Jnana Vistara.
Extracts text from NCERT/State Board PDFs, chunks text page-by-page,
generates BGE-M3 embeddings in batches, and indexes them in local on-disk Qdrant.
"""

import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Suppress HuggingFace hub warnings and enforce offline mode once cached
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ.setdefault("HF_HUB_OFFLINE", "1")

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from core.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION,
    DATA_DIR,
    DEFAULT_CLASS_LEVEL,
    EMBED_DIM,
    EMBED_MODEL,
    MIN_CHUNK_LENGTH,
    QDRANT_PATH,
)

# Registry of known textbook filenames mapped to metadata
BOOKS_METADATA: Dict[str, Dict[str, str]] = {
    "Science_Class8_Ch1.pdf": {
        "subject": "Science",
        "chapter": "Crop Production and Management",
        "class_level": "Class 8",
    },
    "Science_Class8_Ch2.pdf": {
        "subject": "Science",
        "chapter": "Microorganisms: Friend and Foe",
        "class_level": "Class 8",
    },
    "Math_Class8_Ch1.pdf": {
        "subject": "Mathematics",
        "chapter": "Rational Numbers",
        "class_level": "Class 8",
    },
}


def parse_metadata_from_filename(filename: str) -> Dict[str, str]:
    """
    Derives subject, chapter, and class level from a PDF filename.
    Checks BOOKS_METADATA first; otherwise falls back to parsing conventions.
    """
    if filename in BOOKS_METADATA:
        return BOOKS_METADATA[filename].copy()

    stem = Path(filename).stem
    pattern = r"^(?P<subject>[A-Za-z]+)_(?:Class(?P<class_level>\w+)_)?(?:Ch|Chapter)?(?P<chapter>.+)$"
    match = re.match(pattern, stem, re.IGNORECASE)

    if match:
        subject = match.group("subject")
        raw_class = match.group("class_level")
        class_level = f"Class {raw_class}" if raw_class else DEFAULT_CLASS_LEVEL
        chapter_str = match.group("chapter").replace("_", " ").strip()
        if chapter_str.isdigit():
            chapter_str = f"Chapter {chapter_str}"
        return {
            "subject": subject,
            "chapter": chapter_str,
            "class_level": class_level,
        }

    parts = stem.split("_")
    subject = parts[0] if parts else "General"
    chapter = parts[1] if len(parts) > 1 else stem
    return {
        "subject": subject,
        "chapter": chapter,
        "class_level": DEFAULT_CLASS_LEVEL,
    }


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Splits text into sliding window chunks of chunk_size with overlap.
    Filters out chunks smaller than MIN_CHUNK_LENGTH.
    """
    text = text.strip()
    if len(text) < MIN_CHUNK_LENGTH:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    step = chunk_size - overlap

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_LENGTH:
            chunks.append(chunk)
        start += step
        if start >= len(text):
            break

    return chunks


def extract_chunks_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Reads a textbook PDF page-by-page using PyMuPDF and produces text chunks
    with associated metadata payloads.
    """
    meta = parse_metadata_from_filename(pdf_path.name)
    extracted_chunks: List[Dict[str, Any]] = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        print(f"[ERROR] Failed to open PDF '{pdf_path.name}': {exc}", flush=True)
        return []

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_num = page_index + 1
        raw_text = page.get_text("text")

        cleaned_text = "\n".join(
            line.strip() for line in raw_text.splitlines() if line.strip()
        )

        page_chunks = chunk_text(cleaned_text, CHUNK_SIZE, CHUNK_OVERLAP)
        for chunk in page_chunks:
            payload = {
                "text": chunk,
                "subject": meta["subject"],
                "chapter": meta["chapter"],
                "class_level": meta["class_level"],
                "page": page_num,
                "source_file": pdf_path.name,
            }
            extracted_chunks.append(payload)

    doc.close()
    return extracted_chunks


def setup_clean_collection(
    qdrant_path: Path = QDRANT_PATH,
    collection_name: str = COLLECTION,
) -> QdrantClient:
    """
    Recreates the Qdrant collection on local disk to guarantee a clean slate
    without stale or duplicate vectors from previous runs.
    """
    # If collection directory exists, remove it before opening new client
    col_dir = qdrant_path / "collection" / collection_name
    if col_dir.exists():
        shutil.rmtree(col_dir, ignore_errors=True)

    qdrant_path.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(qdrant_path))

    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )
    print(f"[Qdrant] Collection '{collection_name}' initialized (dim={EMBED_DIM}, metric=COSINE).", flush=True)
    return client


def ingest_all_textbooks(
    data_dir: Path = DATA_DIR,
    qdrant_path: Path = QDRANT_PATH,
    collection_name: str = COLLECTION,
) -> int:
    """
    Scans data/textbooks, processes all PDFs, embeds chunks with BGE-M3,
    and indexes them in local Qdrant.
    """
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Ingest] Created textbook directory at {data_dir}. Place PDF files here.", flush=True)
        return 0

    pdf_files = list(data_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[Ingest] No PDF files found in {data_dir}.", flush=True)
        return 0

    print(f"[Ingest] Found {len(pdf_files)} PDF(s) in {data_dir.name}:", flush=True)
    for f in pdf_files:
        print(f"  - {f.name}", flush=True)

    all_payloads: List[Dict[str, Any]] = []
    for pdf in pdf_files:
        chunks = extract_chunks_from_pdf(pdf)
        print(f"[Ingest] '{pdf.name}': extracted {len(chunks)} chunk(s).", flush=True)
        all_payloads.extend(chunks)

    if not all_payloads:
        print("[Ingest] No valid chunks extracted. Ingestion aborted.", flush=True)
        return 0

    print(f"\n[Ingest] Total chunks across all books: {len(all_payloads)}", flush=True)
    print(f"[Embedder] Loading model '{EMBED_MODEL}' (offline mode)...", flush=True)
    is_offline = os.getenv("HF_HUB_OFFLINE", "1") == "1"
    embedder = SentenceTransformer(EMBED_MODEL, local_files_only=is_offline)

    texts = [item["text"] for item in all_payloads]
    print(f"[Embedder] Generating embeddings for {len(texts)} chunks in batches...", flush=True)
    embeddings = embedder.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    client = setup_clean_collection(qdrant_path, collection_name)
    try:
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb.tolist(),
                payload=payload,
            )
            for emb, payload in zip(embeddings, all_payloads)
        ]

        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(collection_name=collection_name, points=batch)

        total_indexed = client.count(collection_name).count
        print(f"[Ingest] Successfully indexed {total_indexed} points into collection '{collection_name}'.", flush=True)
        return total_indexed
    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    count = ingest_all_textbooks()
    print(f"\n[Done] Ingestion complete. Indexed chunks: {count}", flush=True)
