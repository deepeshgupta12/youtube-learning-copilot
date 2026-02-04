# apps/api/app/services/embeddings.py
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

import numpy as np

from sentence_transformers import SentenceTransformer  # type: ignore


DEFAULT_EMBED_MODEL = (
    os.getenv("YLC_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2").strip()
    or "sentence-transformers/all-MiniLM-L6-v2"
)

# Force CPU by default (most stable on macOS Celery workers).
# You can override to "mps" later, but CPU is the reliable baseline.
DEFAULT_EMBED_DEVICE = (os.getenv("YLC_EMBED_DEVICE", "cpu").strip().lower() or "cpu")


def _safe_device(requested: str) -> str:
    """
    Minimal safety guard.
    We don't hard-check torch.backends here to avoid import-time device coupling.
    """
    d = (requested or "cpu").strip().lower()
    if d not in {"cpu", "mps", "cuda"}:
        return "cpu"
    return d


@lru_cache(maxsize=4)
def _load_model(model_name: str, device: str) -> SentenceTransformer:
    """
    Load and cache SentenceTransformer model by (model_name, device).
    all-MiniLM-L6-v2 => 384 dims
    """
    return SentenceTransformer(model_name, device=device)


def _encode(
    model: SentenceTransformer,
    texts: List[str],
    *,
    normalize: bool,
    batch_size: int,
) -> np.ndarray:
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=normalize,
    )
    if isinstance(vecs, list):
        vecs = np.array(vecs, dtype=np.float32)
    return vecs.astype(np.float32)


def embed_texts(
    texts: List[str],
    *,
    model_name: str = DEFAULT_EMBED_MODEL,
    device: Optional[str] = None,
    normalize: bool = True,
    batch_size: int = 64,
) -> List[List[float]]:
    """
    Embed an array of strings -> list of vectors (list[float]).

    Default: CPU (stable on macOS, avoids MTLCompilerService issues).
    If device is "mps" and it fails, auto-fallback to CPU once.
    """
    if not texts:
        return []

    dev = _safe_device(device or DEFAULT_EMBED_DEVICE)

    # First attempt
    try:
        model = _load_model(model_name, dev)
        vecs = _encode(model, texts, normalize=normalize, batch_size=batch_size)
        return vecs.tolist()
    except RuntimeError as e:
        # MPS/Metal failures commonly show up as RuntimeError.
        # Fallback to CPU for robustness.
        if dev != "cpu":
            model_cpu = _load_model(model_name, "cpu")
            vecs = _encode(model_cpu, texts, normalize=normalize, batch_size=batch_size)
            return vecs.tolist()
        raise