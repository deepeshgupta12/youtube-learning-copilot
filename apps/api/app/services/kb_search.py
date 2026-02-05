# apps/api/app/services/kb_search.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from pgvector.sqlalchemy import Vector

from app.models.transcript_chunk import TranscriptChunk
from app.models.transcript_chunk_embedding import TranscriptChunkEmbedding
from app.services.embeddings import embed_texts


@dataclass
class KBSearchItem:
    chunk_id: int
    idx: int
    start_sec: float
    end_sec: float
    text: str
    score: float
    distance: float


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def kb_search_chunks(
    db: Session,
    study_pack_id: int,
    *,
    q: Optional[str] = None,
    query: Optional[str] = None,  # backwards-compatible alias
    limit: int = 5,
    model: str = "sentence-transformers/all-MiniLM-L6-v2",
    hybrid: bool = True,
) -> List[Dict[str, Any]]:
    """
    V2.2 — Hybrid retrieval over transcript chunks.

    Args:
      q: query string (canonical)
      query: alias for q (compat)
      hybrid: if True, blend semantic + lexical; if False, semantic-only
    """
    text_q = (q if q is not None else query) or ""
    text_q = text_q.strip()
    if not text_q:
        return []

    # 1) Semantic search (pgvector)
    # Embed the query locally
    q_vec = embed_texts([text_q], model_name=model, normalize=True)[0]
    dim = len(q_vec)

    # NOTE: We use raw SQL to avoid tight coupling on SQLAlchemy vector operators.
    # distance = embedding <=> query_vec (cosine distance in pgvector)
    # lower distance is better.
    stmt = text(
        """
        SELECT
          tce.chunk_id AS chunk_id,
          tc.idx AS idx,
          tc.start_sec AS start_sec,
          tc.end_sec AS end_sec,
          tc.text AS text,
          (1.0 - (tce.embedding <=> :qvec)) AS score,
          (tce.embedding <=> :qvec) AS distance
        FROM transcript_chunk_embeddings tce
        JOIN transcript_chunks tc ON tc.id = tce.chunk_id
        WHERE tce.study_pack_id = :study_pack_id
          AND tce.model = :model
          AND tce.dim = :dim
        ORDER BY tce.embedding <=> :qvec
        LIMIT :k
        """
    ).bindparams(
        bindparam("qvec", type_=Vector(dim))
    )

    sem_rows = db.execute(
        stmt,
        {
            "qvec": q_vec,
            "study_pack_id": study_pack_id,
            "model": model,
            "dim": dim,
            "k": limit,
        },
    ).mappings().all()

    # Convert semantic rows to dicts
    sem_items: List[Dict[str, Any]] = []
    for r in sem_rows:
        sem_items.append(
            {
                "chunk_id": int(r.chunk_id),
                "idx": int(r.idx),
                "start_sec": _safe_float(r.start_sec),
                "end_sec": _safe_float(r.end_sec),
                "text": str(r.text),
                "score": _safe_float(r.score),
                "distance": _safe_float(r.distance),
            }
        )

    if not hybrid:
        return sem_items[:limit]

    # 2) Lexical boost (simple ILIKE, small candidate pool)
    # Use a tiny bag-of-words match over transcript_chunks text.
    # Then blend by bumping score if chunk appears lexically relevant.
    tokens = [t for t in text_q.lower().replace(":", " ").replace(",", " ").split() if len(t) >= 3]
    tokens = tokens[:8]  # cap to keep query sane
    if not tokens:
        return sem_items[:limit]

    lex_query = db.query(TranscriptChunk).filter(TranscriptChunk.study_pack_id == study_pack_id)
    for t in tokens:
        lex_query = lex_query.filter(TranscriptChunk.text.ilike(f"%{t}%"))

    lex_rows = lex_query.order_by(TranscriptChunk.idx.asc()).limit(limit * 3).all()
    lex_ids = {int(x.id) for x in lex_rows}

    # Blend:
    # - start with semantic
    # - boost if chunk appears in lexical set
    for it in sem_items:
        if int(it["chunk_id"]) in lex_ids:
            it["score"] = float(it["score"]) + 0.08  # small boost

    sem_items.sort(key=lambda d: float(d["score"]), reverse=True)
    return sem_items[:limit]