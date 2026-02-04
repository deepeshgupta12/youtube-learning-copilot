# app/services/kb_search.py
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.transcript_chunk import TranscriptChunk
from app.models.transcript_chunk_embedding import TranscriptChunkEmbedding
from app.services.embeddings import embed_texts


def _tokens_for_hybrid(q: str) -> List[str]:
    """
    Turn a query into useful keyword tokens.
    Keep it simple + robust:
    - lowercase
    - alnum tokens
    - drop very small tokens
    - cap token count (avoid huge OR)
    """
    q = (q or "").lower()
    toks = re.findall(r"[a-z0-9]+", q)
    toks = [t for t in toks if len(t) >= 3]
    # dedupe preserving order
    seen = set()
    out = []
    for t in toks:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:8]


def kb_search_chunks(
    db: Session,
    study_pack_id: int,
    query: str,
    model: str,
    limit: int = 8,
    use_hybrid: bool = True,
) -> List[dict]:
    """
    Returns top chunks for a query using pgvector cosine distance.
    Hybrid = additionally filter candidates by keyword tokens.
    """

    q = (query or "").strip()
    if not q:
        raise ValueError("Query is required")

    # 1) Ensure embeddings exist for this pack+model
    exists = (
        db.query(TranscriptChunkEmbedding.id)
        .filter(
            TranscriptChunkEmbedding.study_pack_id == study_pack_id,
            TranscriptChunkEmbedding.model == model,
        )
        .limit(1)
        .first()
    )
    if not exists:
        raise RuntimeError(
            f"No embeddings found for study_pack_id={study_pack_id} model={model}. "
            f"Run POST /study-packs/{study_pack_id}/kb/embed first."
        )

    # 2) Embed the query (CPU-safe; you already stabilized embeddings.py)
    qvec = embed_texts([q], model_name=model, normalize=True)[0]

    # 3) Build SQL query
    # cosine_distance: lower = more similar
    dist = TranscriptChunkEmbedding.embedding.cosine_distance(qvec)

    qry = (
        db.query(
            TranscriptChunkEmbedding.chunk_id.label("chunk_id"),
            TranscriptChunk.idx.label("idx"),
            TranscriptChunk.start_sec.label("start_sec"),
            TranscriptChunk.end_sec.label("end_sec"),
            TranscriptChunk.text.label("text"),
            dist.label("distance"),
        )
        .join(TranscriptChunk, TranscriptChunk.id == TranscriptChunkEmbedding.chunk_id)
        .filter(
            TranscriptChunkEmbedding.study_pack_id == study_pack_id,
            TranscriptChunkEmbedding.model == model,
        )
    )

    # 4) Hybrid keyword filter (simple + fast)
    if use_hybrid:
        toks = _tokens_for_hybrid(q)
        if toks:
            ors = [TranscriptChunk.text.ilike(f"%{t}%") for t in toks]
            qry = qry.filter(or_(*ors))

    rows = qry.order_by(dist.asc()).limit(limit).all()

    out = []
    for r in rows:
        distance = float(r.distance)
        # cosine similarity ~= 1 - cosine_distance
        score = 1.0 - distance
        out.append(
            {
                "chunk_id": int(r.chunk_id),
                "idx": int(r.idx),
                "start_sec": float(r.start_sec),
                "end_sec": float(r.end_sec),
                "text": r.text,
                "score": float(score),
                "distance": float(distance),
            }
        )

    # If hybrid got nothing, fallback to pure vector search
    if use_hybrid and not out:
        rows = (
            db.query(
                TranscriptChunkEmbedding.chunk_id.label("chunk_id"),
                TranscriptChunk.idx.label("idx"),
                TranscriptChunk.start_sec.label("start_sec"),
                TranscriptChunk.end_sec.label("end_sec"),
                TranscriptChunk.text.label("text"),
                dist.label("distance"),
            )
            .join(TranscriptChunk, TranscriptChunk.id == TranscriptChunkEmbedding.chunk_id)
            .filter(
                TranscriptChunkEmbedding.study_pack_id == study_pack_id,
                TranscriptChunkEmbedding.model == model,
            )
            .order_by(dist.asc())
            .limit(limit)
            .all()
        )

        out = []
        for r in rows:
            distance = float(r.distance)
            score = 1.0 - distance
            out.append(
                {
                    "chunk_id": int(r.chunk_id),
                    "idx": int(r.idx),
                    "start_sec": float(r.start_sec),
                    "end_sec": float(r.end_sec),
                    "text": r.text,
                    "score": float(score),
                    "distance": float(distance),
                }
            )

    return out