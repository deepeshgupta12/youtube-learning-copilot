# apps/api/app/worker/embedding_tasks.py
from __future__ import annotations

import json
import time
from typing import Optional

from celery import shared_task
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.job import Job
from app.models.study_pack import StudyPack
from app.models.transcript_chunk import TranscriptChunk
from app.models.transcript_chunk_embedding import TranscriptChunkEmbedding
from app.services.embeddings import DEFAULT_EMBED_MODEL, embed_texts


def _db() -> Session:
    return SessionLocal()


def _set_job_running(db: Session, job_id: int, payload: dict) -> None:
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        return
    j.status = "running"
    j.payload_json = json.dumps(payload)
    j.error = None
    db.commit()


def _set_job_done(db: Session, job_id: int, payload: dict) -> None:
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        return
    j.status = "done"
    j.payload_json = json.dumps(payload)
    j.error = None
    db.commit()


def _set_job_failed(db: Session, job_id: int, err: str, payload: dict | None = None) -> None:
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        return
    j.status = "failed"
    j.error = err
    if payload is not None:
        j.payload_json = json.dumps(payload)
    db.commit()


@shared_task(name="kb.embed_transcript_chunks")
def embed_transcript_chunks(job_id: int, study_pack_id: int, model_name: Optional[str] = None) -> dict:
    """
    Embed all transcript_chunks for a given study_pack and store into transcript_chunk_embeddings.

    Upsert key:
      (chunk_id, model)
    """
    t0 = time.time()
    model = (model_name or DEFAULT_EMBED_MODEL).strip()

    db = _db()
    try:
        sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
        if not sp:
            _set_job_failed(db, job_id, f"StudyPack {study_pack_id} not found")
            return {"ok": False, "error": f"StudyPack {study_pack_id} not found"}

        _set_job_running(db, job_id, {"stage": "embedding", "study_pack_id": study_pack_id, "model": model})

        # Load chunks in order
        chunks = (
            db.query(TranscriptChunk)
            .filter(TranscriptChunk.study_pack_id == study_pack_id)
            .order_by(TranscriptChunk.idx.asc())
            .all()
        )

        if not chunks:
            _set_job_failed(db, job_id, "No transcript chunks found for study pack")
            return {"ok": False, "error": "No transcript chunks found for study pack"}

        texts = [c.text for c in chunks]
        vecs = embed_texts(texts, model_name=model, normalize=True)

        # basic sanity on dims
        dim = len(vecs[0]) if vecs else 0
        if dim != 384:
            _set_job_failed(db, job_id, f"Unexpected embedding dim={dim} (expected 384) for model={model}")
            return {"ok": False, "error": f"Unexpected embedding dim={dim} (expected 384)"}

        # Upsert rows
        # Use PostgreSQL INSERT ... ON CONFLICT for speed and idempotency.
        # The table has UniqueConstraint(chunk_id, model).
        rows = []
        for c, v in zip(chunks, vecs):
            rows.append(
                {
                    "study_pack_id": int(study_pack_id),
                    "chunk_id": int(c.id),
                    "model": model,
                    "dim": int(dim),
                    "embedding": v,
                }
            )

        if rows:
            stmt = pg_insert(TranscriptChunkEmbedding.__table__).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_chunk_embeddings_chunk_model",
                set_={
                    "study_pack_id": stmt.excluded.study_pack_id,
                    "dim": stmt.excluded.dim,
                    "embedding": stmt.excluded.embedding,
                    "updated_at": func.now(),
                },
            )
            db.execute(stmt)
            db.commit()

        elapsed_ms = int((time.time() - t0) * 1000)

        # Compute counts
        total_chunks = len(chunks)
        embedded = (
            db.execute(
                select(func.count(TranscriptChunkEmbedding.id)).where(
                    TranscriptChunkEmbedding.study_pack_id == study_pack_id,
                    TranscriptChunkEmbedding.model == model,
                )
            )
            .scalar_one()
        )

        payload = {
            "stage": "done",
            "study_pack_id": study_pack_id,
            "model": model,
            "dim": dim,
            "total_chunks": total_chunks,
            "embedded": int(embedded or 0),
            "elapsed_ms": elapsed_ms,
        }
        _set_job_done(db, job_id, payload)

        return {"ok": True, **payload}

    except Exception as e:
        _set_job_failed(db, job_id, str(e))
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass