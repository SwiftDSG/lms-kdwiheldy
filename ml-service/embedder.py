"""
embedder.py — Loads pre-computed question embeddings and runs cosine similarity
              search to find the most relevant examples for a given query.

The embedding model used is `intfloat/multilingual-e5-small`:
  - 117M parameters, 384-dimensional output
  - Supports Indonesian natively (trained on 100+ languages)
  - e5 models require a task prefix: "query: ..." for search, "passage: ..." for docs

HOW COSINE SIMILARITY WORKS:
  Two vectors are "similar" if they point in the same direction.
  cosine_similarity = dot(A, B) / (|A| × |B|)
  Range: -1 (opposite) to +1 (identical). We want the highest scores.
  Pre-normalizing vectors reduces this to a simple dot product, which is fast.
"""

from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

# ── Paths ──────────────────────────────────────────────────────────────────────

DATA_DIR        = Path(__file__).parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
META_PATH       = DATA_DIR / "questions_meta.json"

EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


# ── Embedder class ─────────────────────────────────────────────────────────────

class Embedder:
    """
    Manages the embedding model and the in-memory vector store.

    At 400 questions × 384 dimensions × 4 bytes = ~600 KB in memory.
    No need for a vector database at this scale — a numpy dot product
    over all 400 vectors takes under 1 ms.
    """

    def __init__(self) -> None:
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        # device=None lets sentence-transformers pick CPU/MPS/CUDA automatically
        self.model = SentenceTransformer(EMBEDDING_MODEL)

        if not EMBEDDINGS_PATH.exists() or not META_PATH.exists():
            raise FileNotFoundError(
                "Pre-computed embeddings not found. "
                "Run embed_questions.py first:\n"
                "  python embed_questions.py"
            )

        print("Loading pre-computed embeddings from disk...")
        # Shape: (N, 384) — one row per question, already L2-normalized
        self.embeddings: np.ndarray = np.load(str(EMBEDDINGS_PATH))

        with open(META_PATH, encoding="utf-8") as f:
            self.questions: list[dict] = json.load(f)

        assert len(self.embeddings) == len(self.questions), (
            f"Embedding count ({len(self.embeddings)}) != "
            f"question count ({len(self.questions)}). Re-run embed_questions.py."
        )

        print(f"Ready: {len(self.questions)} questions loaded.")

    def embed_query(self, text: str) -> np.ndarray:
        """
        Embed a single query string.
        e5 models require the "query: " prefix for search queries.
        Returns a 1-D normalized vector of shape (384,).
        """
        vec = self.model.encode(
            f"query: {text}",
            normalize_embeddings=True,  # L2 normalize so dot product = cosine sim
        )
        return vec  # shape: (384,)

    def search(self, query_text: str, top_k: int = 3) -> list[dict]:
        """
        Find the top_k most similar questions to query_text.

        Returns a list of question metadata dicts, each containing:
          content, options_str, explanation, tip (if present), category
        """
        query_vec = self.embed_query(query_text)

        # Dot product against all rows — gives cosine similarity for each question
        # Shape: (N,)
        scores = self.embeddings @ query_vec

        # Get indices of top_k highest scores (argsort ascending, take last k, flip)
        top_indices = np.argsort(scores)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            meta = self.questions[idx].copy()
            meta["score"] = float(scores[idx])
            results.append(meta)

        return results
