# apps/api/app/services/embeddings.py
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

import numpy as np

# SentenceTransformers is optional until you run V2.1
# pip install sentence-transformers
from sentence_transformers import SentenceTransformer  # type: ignore


DEFAULT_EMBED_MODEL = os.getenv(
    "YLC_EMBED_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
).strip() or "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> SentenceTransformer:
    """
    Load and cache SentenceTransformer model.

    IMPORTANT:
    - all-MiniLM-L6-v2 => 384 dims
    - caches across tasks inside the worker process
    """
    return SentenceTransformer(model_name)


def embed_texts(
    texts: List[str],
    *,
    model_name: str = DEFAULT_EMBED_MODEL,
    normalize: bool = True,
    batch_size: int = 64,
) -> List[List[float]]:
    """
    Embed an array of strings -> list of vectors (list[float]).
    Normalization helps cosine similarity behave well.
    """
    if not texts:
        return []

    model = _load_model(model_name)

    # SentenceTransformer returns numpy array if convert_to_numpy=True
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=normalize,
    )

    if isinstance(vecs, list):
        vecs = np.array(vecs, dtype=np.float32)

    # Ensure python floats for JSON/DB safety
    return vecs.astype(np.float32).tolist()