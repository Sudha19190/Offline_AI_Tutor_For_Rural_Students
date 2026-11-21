"""
core/retriever.py - Hybrid retrieval engine for Jnana Vistara.
Combines dense semantic search (BAAI/bge-m3 via local Qdrant) with sparse
keyword search (BM25 via rank_bm25) merged using Reciprocal Rank Fusion (RRF).
"""

import os
import re
from typing import Any, Dict, List, Optional

# Enforce offline mode for HuggingFace embedding model
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from core.config import (
    COLLECTION,
    EMBED_MODEL,
    QDRANT_PATH,
    TOP_K,
)

# Global in-memory cache for BM25 and embedder
_EMBEDDER: Optional[SentenceTransformer] = None
_BM25_INDEX: Optional[BM25Okapi] = None
_CORPUS_PAYLOADS: List[Dict[str, Any]] = []


def get_embedder() -> SentenceTransformer:
    """Returns singleton SentenceTransformer embedder instance."""
    global _EMBEDDER
    if _EMBEDDER is None:
        is_offline = os.getenv("HF_HUB_OFFLINE", "1") == "1"
        _EMBEDDER = SentenceTransformer(EMBED_MODEL, local_files_only=is_offline)
    return _EMBEDDER


def tokenize(text: str) -> List[str]:
    """Simple alphanumeric tokenizer for BM25."""
    return re.findall(r"\w+", text.lower())


def get_qdrant_client() -> QdrantClient:
    """Returns an open QdrantClient connected to local on-disk database."""
    return QdrantClient(path=str(QDRANT_PATH))


def build_bm25_index() -> None:
    """
    Loads all chunk payloads from Qdrant and constructs the in-memory BM25 index.
    Called on startup and can be refreshed after new textbook ingestion.
    """
    global _BM25_INDEX, _CORPUS_PAYLOADS
    client = get_qdrant_client()
    try:
        if not client.collection_exists(COLLECTION):
            _BM25_INDEX = None
            _CORPUS_PAYLOADS = []
            return

        points, _ = client.scroll(
            collection_name=COLLECTION,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )

        _CORPUS_PAYLOADS = [
            {
                "id": p.id,
                "text": p.payload.get("text", ""),
                "subject": p.payload.get("subject", ""),
                "chapter": p.payload.get("chapter", ""),
                "class_level": p.payload.get("class_level", ""),
                "page": p.payload.get("page", 1),
                "source_file": p.payload.get("source_file", ""),
            }
            for p in points
        ]

        if _CORPUS_PAYLOADS:
            tokenized_corpus = [tokenize(item["text"]) for item in _CORPUS_PAYLOADS]
            _BM25_INDEX = BM25Okapi(tokenized_corpus)
        else:
            _BM25_INDEX = None
    finally:
        client.close()


def ensure_bm25_index() -> None:
    """Ensures BM25 index is populated."""
    if _BM25_INDEX is None:
        build_bm25_index()


def build_payload_filter(
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
) -> Optional[Filter]:
    """Constructs Qdrant Filter for subject and chapter metadata."""
    must_conditions = []
    if subject:
        must_conditions.append(
            FieldCondition(key="subject", match=MatchValue(value=subject))
        )
    if chapter:
        must_conditions.append(
            FieldCondition(key="chapter", match=MatchValue(value=chapter))
        )

    if must_conditions:
        return Filter(must=must_conditions)
    return None


def dense_search(
    client: QdrantClient,
    query_vector: List[float],
    query_filter: Optional[Filter] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Executes dense cosine vector search in Qdrant."""
    res = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
    )

    results = []
    for p in res.points:
        payload = p.payload or {}
        results.append({
            "id": p.id,
            "text": payload.get("text", ""),
            "page": payload.get("page", 1),
            "chapter": payload.get("chapter", ""),
            "subject": payload.get("subject", ""),
            "class_level": payload.get("class_level", ""),
            "source_file": payload.get("source_file", ""),
            "score": float(p.score) if p.score is not None else 0.0,
        })
    return results


def bm25_search(
    question: str,
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Executes keyword BM25 search over in-memory corpus with optional filtering."""
    ensure_bm25_index()
    if _BM25_INDEX is None or not _CORPUS_PAYLOADS:
        return []

    tokens = tokenize(question)
    if not tokens:
        return []

    scores = _BM25_INDEX.get_scores(tokens)

    # Filter candidates by subject/chapter if specified
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    filtered_results = []
    for idx in ranked_indices:
        item = _CORPUS_PAYLOADS[idx]
        if subject and item.get("subject") != subject:
            continue
        if chapter and item.get("chapter") != chapter:
            continue
        if scores[idx] <= 0.0:
            continue

        res_item = item.copy()
        res_item["bm25_score"] = float(scores[idx])
        filtered_results.append(res_item)
        if len(filtered_results) >= limit:
            break

    return filtered_results


def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    k: int = TOP_K,
    rrf_k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Merges dense and BM25 results using Reciprocal Rank Fusion.
    Score = sum(1.0 / (rrf_k + rank)).
    Preserves dense score for threshold filtering.
    """
    rrf_map: Dict[Any, float] = {}
    item_map: Dict[Any, Dict[str, Any]] = {}

    for rank, item in enumerate(dense_results, start=1):
        doc_id = item["id"]
        rrf_map[doc_id] = rrf_map.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))
        item_map[doc_id] = item

    for rank, item in enumerate(bm25_results, start=1):
        doc_id = item["id"]
        rrf_map[doc_id] = rrf_map.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))
        if doc_id not in item_map:
            # If item was only found in BM25, give it zero dense score placeholder
            item_copy = item.copy()
            item_copy["score"] = 0.0
            item_map[doc_id] = item_copy

    sorted_ids = sorted(rrf_map.keys(), key=lambda did: rrf_map[did], reverse=True)

    fused_results = []
    for did in sorted_ids[:k]:
        item = item_map[did].copy()
        item["rrf_score"] = rrf_map[did]
        fused_results.append({
            "text": item["text"],
            "page": item["page"],
            "chapter": item["chapter"],
            "subject": item["subject"],
            "score": item["score"],
            "rrf_score": item["rrf_score"],
        })

    return fused_results


def retrieve(
    question: str,
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    k: int = TOP_K,
    hybrid: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retrieves the top-k most relevant textbook chunks for a student question.

    Args:
        question: Student's natural language question.
        subject: Optional subject filter (e.g. "Science").
        chapter: Optional chapter filter (e.g. "Crop Production and Management").
        k: Number of chunks to return (default TOP_K=4).
        hybrid: If True, merges dense (BGE-M3) and BM25 with RRF.
                If False, runs dense retrieval only (used for ablation evaluation).

    Returns:
        List of dicts containing {text, page, chapter, subject, score}.
    """
    client = get_qdrant_client()
    try:
        embedder = get_embedder()
        query_vector = embedder.encode(
            question,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        q_filter = build_payload_filter(subject=subject, chapter=chapter)
        candidate_limit = max(k * 3, 10)

        dense_res = dense_search(
            client=client,
            query_vector=query_vector,
            query_filter=q_filter,
            limit=candidate_limit,
        )

        if not hybrid:
            # Dense only ablation
            return [
                {
                    "text": item["text"],
                    "page": item["page"],
                    "chapter": item["chapter"],
                    "subject": item["subject"],
                    "score": item["score"],
                }
                for item in dense_res[:k]
            ]

        # Hybrid: Dense + BM25 with RRF
        bm25_res = bm25_search(
            question=question,
            subject=subject,
            chapter=chapter,
            limit=candidate_limit,
        )

        return reciprocal_rank_fusion(dense_res, bm25_res, k=k)
    finally:
        client.close()


# Initialize BM25 on module import
build_bm25_index()
