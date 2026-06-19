"""
embed_questions.py — Pre-compute and save question embeddings from MongoDB.

Reads all questions from the `quizzes` collection and produces:
  data/embeddings.npy       — (N, 384) float32 matrix, L2-normalized
  data/questions_meta.json  — question metadata for RAG retrieval

Re-run whenever questions are added or updated in the database.

USAGE:
  python embed_questions.py

ENVIRONMENT:
  MONGODB_URI   MongoDB connection string  (default: mongodb://localhost:27017)
  MONGODB_DB    Database name              (default: lms)
"""

import json
import os
import re
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient

# ── Configuration ──────────────────────────────────────────────────────────────

MONGODB_URI     = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB      = os.getenv("MONGODB_DB", "lms")

DATA_DIR        = Path(__file__).parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
META_PATH       = DATA_DIR / "questions_meta.json"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


# ── LaTeX cleaning (same as before) ───────────────────────────────────────────

def clean_latex(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    for _ in range(5):
        prev = text
        text = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}', r'\1/\2', text)
        if text == prev:
            break
    text = text.replace(r'\times', '×').replace(r'\div', '÷')
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', text)
    text = re.sub(r'\^\{([^}]*)\}', r'^(\1)', text)
    text = text.replace('$', '')
    return re.sub(r' +', ' ', text).strip()


# ── Build text to embed for each question ──────────────────────────────────────

def question_to_embed_text(q: dict) -> str:
    """
    Produces the text that gets embedded for a question.
    Includes question content + all option labels/content so that
    similarity search matches on both topic and answer structure.
    """
    content = clean_latex(q["content"])
    options = " | ".join(
        f"{o['label']}. {clean_latex(o['content'])}"
        for o in q.get("options", [])
    )
    return f"{content} {options}".strip()


# ── Build metadata stored alongside each embedding ────────────────────────────

def build_meta(q: dict, category: str, source: str) -> dict:
    """
    Stores the data injected into the LLM prompt as a few-shot example.
    `tip` is not in the DB schema (it's LLM-generated), so it defaults to "".
    """
    correct = next((o for o in q.get("options", []) if o.get("is_correct")), None)

    return {
        "source":        source,
        "category":      category,
        "content":       clean_latex(q["content"]),
        "options_str":   " | ".join(
            f"{o['label']}. {clean_latex(o['content'])}"
            for o in q.get("options", [])
        ),
        "correct_label": correct["label"] if correct else "",
        "correct_text":  clean_latex(correct["content"]) if correct else "",
        "explanation":   clean_latex(q.get("explanation") or ""),
        "tip":           q.get("tip") or "",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Connecting to MongoDB: {MONGODB_URI} / {MONGODB_DB}")
    client = MongoClient(MONGODB_URI)
    db     = client[MONGODB_DB]

    quiz_sets = list(db.quizzes.find({}))
    if not quiz_sets:
        print("No quiz sets found in the database. Import questions first.")
        client.close()
        return

    print(f"Found {len(quiz_sets)} quiz set(s)\n")

    texts: list[str] = []
    metas: list[dict] = []

    for qs in quiz_sets:
        category = qs.get("category", "UNKNOWN")
        source   = qs.get("title") or qs.get("id", "unknown")
        count    = 0
        for q in qs.get("questions", []):
            if not q.get("options"):
                continue
            texts.append(question_to_embed_text(q))
            metas.append(build_meta(q, category, source))
            count += 1
        print(f"  [{category}] {source}: {count} questions")

    client.close()

    if not texts:
        print("\nNo embeddable questions found (all questions need at least one option).")
        return

    print(f"\nTotal: {len(texts)} questions to embed")
    print(f"Loading model: {EMBEDDING_MODEL}")
    print("  (first run downloads ~120 MB to ~/.cache/huggingface/)\n")

    model = SentenceTransformer(EMBEDDING_MODEL)

    # e5 models require "passage: " prefix for documents being indexed
    prefixed = [f"passage: {t}" for t in texts]

    print("Computing embeddings (this takes ~10s on CPU)...")
    embeddings = model.encode(
        prefixed,
        normalize_embeddings=True,  # L2-normalize so dot product = cosine sim
        show_progress_bar=True,
        batch_size=32,
    )
    # embeddings shape: (N, 384), dtype float32

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.save(str(EMBEDDINGS_PATH), embeddings)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False, indent=2)

    print(f"\nSaved:")
    print(f"  {EMBEDDINGS_PATH}  ({embeddings.nbytes // 1024} KB)")
    print(f"  {META_PATH}")
    print(f"\nEmbedding shape: {embeddings.shape}")
    print("Done. Run serve.py to start the API.")


if __name__ == "__main__":
    main()
