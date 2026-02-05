# apps/api/app/services/kb_search.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.models.transcript_chunk import TranscriptChunk
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


def _to_pgvector_literal(vec: List[float]) -> str:
    """
    Convert list[float] -> pgvector literal string: "[0.1,0.2,...]".
    This avoids psycopg sending it as double precision[] (array), which breaks <=>.
    """
    return "[" + ",".join(f"{float(v):.8f}" for v in vec) + "]"


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
    q_vec = embed_texts([text_q], model_name=model, normalize=True)[0]
    dim = len(q_vec)
    qvec_literal = _to_pgvector_literal([float(x) for x in q_vec])

    # Important:
    # - bind :qvec as TEXT and cast to ::vector in SQL
    # - otherwise psycopg sends python list as double precision[] and pgvector <=> fails
    stmt = text(
        """
        SELECT
          tce.chunk_id AS chunk_id,
          tc.idx AS idx,
          tc.start_sec AS start_sec,
          tc.end_sec AS end_sec,
          tc.text AS text,
          (1.0 - (tce.embedding <=> (:qvec)::vector)) AS score,
          (tce.embedding <=> (:qvec)::vector) AS distance
        FROM transcript_chunk_embeddings tce
        JOIN transcript_chunks tc ON tc.id = tce.chunk_id
        WHERE tce.study_pack_id = :study_pack_id
          AND tce.model = :model
          AND tce.dim = :dim
        ORDER BY tce.embedding <=> (:qvec)::vector
        LIMIT :k
        """
    ).bindparams(
        bindparam("qvec"),
        bindparam("study_pack_id"),
        bindparam("model"),
        bindparam("dim"),
        bindparam("k"),
    )

    sem_rows = (
        db.execute(
            stmt,
            {
                "qvec": qvec_literal,
                "study_pack_id": study_pack_id,
                "model": model,
                "dim": dim,
                "k": int(limit),
            },
        )
        .mappings()
        .all()
    )

    sem_items: List[Dict[str, Any]] = []
    for r in sem_rows:
        sem_items.append(
            {
                "chunk_id": int(r["chunk_id"]),
                "idx": int(r["idx"]),
                "start_sec": _safe_float(r["start_sec"]),
                "end_sec": _safe_float(r["end_sec"]),
                "text": str(r["text"]),
                "score": _safe_float(r["score"]),
                "distance": _safe_float(r["distance"]),
            }
        )

    if not hybrid:
        return sem_items[:limit]

    # 2) Lexical boost (simple ILIKE, small candidate pool)
    tokens = [
        t
        for t in text_q.lower().replace(":", " ").replace(",", " ").split()
        if len(t) >= 3
    ][:8]
    if not tokens:
        return sem_items[:limit]

    lex_query = db.query(TranscriptChunk).filter(
        TranscriptChunk.study_pack_id == study_pack_id
    )
    for t in tokens:
        lex_query = lex_query.filter(TranscriptChunk.text.ilike(f"%{t}%"))

    lex_rows = lex_query.order_by(TranscriptChunk.idx.asc()).limit(limit * 3).all()
    lex_ids = {int(x.id) for x in lex_rows}

    for it in sem_items:
        if int(it["chunk_id"]) in lex_ids:
            it["score"] = float(it["score"]) + 0.08

    sem_items.sort(key=lambda d: float(d["score"]), reverse=True)
    return sem_items[:limit]