"""
core/config.py - Central configuration for Jnana Vistara.
All paths, model names, and retrieval parameters are defined here.
Offline-first: no cloud APIs, no internet needed at runtime.
"""

import os
from pathlib import Path

# Enforce HuggingFace offline mode for local inference
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "textbooks"
QDRANT_PATH = BASE_DIR / "qdrant_db"
SQLITE_PATH = BASE_DIR / "app.db"

# LLM & Embedding Models
# Default model in Ollama is phi3:latest (configurable via env var, e.g. qwen2.5:3b)
LLM_MODEL = os.getenv("LLM_MODEL", "phi3:latest")

# Embedding model: BAAI/bge-m3 (1024-dim, multilingual, normalized, no query/passage prefixes)
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM = 1024

# Qdrant Vector DB Collection Name
COLLECTION = "textbook"

# Chunking Configuration
CHUNK_SIZE = 800       # Chunk length in characters
CHUNK_OVERLAP = 150    # Overlap between consecutive chunks in characters
MIN_CHUNK_LENGTH = 60  # Skip very short chunks (headers, page numbers, etc.)

# Retrieval Parameters
TOP_K = 4

# NOTE: SCORE_THRESHOLD must be tuned based on evaluation and similarity distribution.
# With cosine similarity on normalized bge-m3 vectors, 0.45 acts as the default relevance floor.
# Chunks scoring below this are filtered out, triggering the NOT_FOUND fallback.
SCORE_THRESHOLD = 0.48

# Defaults for student session
DEFAULT_LANGUAGE = "English"
DEFAULT_CLASS_LEVEL = "Class 8"
