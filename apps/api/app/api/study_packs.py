# apps/api/app/api/study_packs.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models.transcript_chunk import TranscriptChunk
from app.models.transcript_chunk_embedding import TranscriptChunkEmbedding
from app.db.session import get_db
from app.models.study_pack import StudyPack
from app.services.jobs import create_job
from app.services.study_packs import create_study_pack
from app.services.youtube import (
    extract_youtube_video_id,
    extract_youtube_playlist_id,
    fetch_playlist_metadata,
    build_video_url,
)
from app.worker.ingest_tasks import ingest_youtube_captions, ingest_youtube_playlist
from app.worker.embedding_tasks import embed_transcript_chunks  # Celery task

# V2.2 Retrieval service
from app.services.kb_search import kb_search_chunks

# V2.3+ Q&A service
from app.services.kb_qa import ask_grounded

router = APIRouter(prefix="/study-packs", tags=["study_packs"])


# -----------------------
# Helpers
# -----------------------
def _with_timestamp(url: str, sec: float) -> str:
    """
    Returns a YouTube URL with a timestamp parameter.
    Works for:
      - ...watch?v=...&list=...
      - ...watch?v=...
    Uses 't=' in seconds.
    """
    base = (url or "").strip()
    if not base:
        return base
    try:
        t = int(max(0.0, float(sec)))
    except Exception:
        t = 0

    sep = "&" if "?" in base else "?"
    # avoid duplicate t=
    if "t=" in base:
        return base
    return f"{base}{sep}t={t}"


# -----------------------
# V1 — Study Packs Library
# -----------------------
class StudyPackFromYoutubeRequest(BaseModel):
    url: str
    language: str | None = None


class StudyPackFromYoutubeResponse(BaseModel):
    ok: bool
    study_pack_id: int
    job_id: int
    task_id: str
    video_id: str | None = None

    # playlist support (optional)
    playlist_id: str | None = None
    playlist_title: str | None = None
    playlist_count: int | None = None


@router.get("")
def list_study_packs(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(StudyPack)

    if status:
        query = query.filter(StudyPack.status == status)

    if source_type:
        query = query.filter(StudyPack.source_type == source_type)

    if q and q.strip():
        s = f"%{q.strip()}%"
        query = query.filter(
            or_(
                StudyPack.title.ilike(s),
                StudyPack.source_url.ilike(s),
                StudyPack.source_id.ilike(s),
                StudyPack.playlist_title.ilike(s),
                StudyPack.playlist_id.ilike(s),
            )
        )

    total = query.count()
    rows = (
        query.order_by(StudyPack.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    packs = []
    for sp in rows:
        packs.append(
            {
                "id": sp.id,
                "title": sp.title,
                "source_type": sp.source_type,
                "source_url": sp.source_url,
                "status": sp.status,
                "source_id": sp.source_id,
                "language": sp.language,
                "playlist_id": sp.playlist_id,
                "playlist_title": sp.playlist_title,
                "playlist_index": sp.playlist_index,
                "error": sp.error,
                "created_at": sp.created_at.isoformat() if sp.created_at else None,
                "updated_at": sp.updated_at.isoformat() if sp.updated_at else None,
            }
        )

    return {"ok": True, "total": total, "limit": limit, "offset": offset, "packs": packs}


@router.post("/from-youtube", response_model=StudyPackFromYoutubeResponse)
def create_from_youtube(
    req: StudyPackFromYoutubeRequest,
    db: Session = Depends(get_db),
) -> StudyPackFromYoutubeResponse:
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    video_id = extract_youtube_video_id(url)
    if video_id:
        sp = create_study_pack(
            db,
            source_type="youtube_video",
            source_url=url,
            source_id=video_id,
            language=req.language,
        )

        job = create_job(
            db,
            "ingest_youtube_captions",
            {"study_pack_id": sp.id, "video_id": video_id},
        )
        async_result = ingest_youtube_captions.delay(job.id, sp.id, video_id, req.language)

        return StudyPackFromYoutubeResponse(
            ok=True,
            study_pack_id=sp.id,
            job_id=job.id,
            task_id=async_result.id,
            video_id=video_id,
        )

    playlist_id = extract_youtube_playlist_id(url)
    if not playlist_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL (not a video or playlist)")

    meta = fetch_playlist_metadata(url, max_items=200)
    playlist_title = meta.get("playlist_title")
    entries = meta.get("entries") or []

    created_ids: list[int] = []
    for e in entries:
        vid = e["video_id"]
        idx = e["index"]
        title = e.get("title")

        sp = create_study_pack(
            db,
            source_type="youtube_video",
            source_url=build_video_url(vid, playlist_id=playlist_id, playlist_index=idx),
            source_id=vid,
            language=req.language,
        )

        sp.playlist_id = playlist_id
        sp.playlist_title = playlist_title
        sp.playlist_index = idx
        if title and not sp.title:
            sp.title = title

        db.commit()
        db.refresh(sp)
        created_ids.append(sp.id)

    if not created_ids:
        raise HTTPException(status_code=400, detail="Playlist has no usable video entries")

    job = create_job(
        db,
        "ingest_youtube_playlist",
        {"playlist_id": playlist_id, "study_pack_ids": created_ids, "url": url},
    )
    async_result = ingest_youtube_playlist.delay(job.id, playlist_id, created_ids, req.language)

    return StudyPackFromYoutubeResponse(
        ok=True,
        study_pack_id=created_ids[0],
        job_id=job.id,
        task_id=async_result.id,
        video_id=None,
        playlist_id=playlist_id,
        playlist_title=playlist_title,
        playlist_count=len(created_ids),
    )


@router.get("/{study_pack_id}")
def get_study_pack(study_pack_id: int, db: Session = Depends(get_db)):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    return {
        "ok": True,
        "study_pack": {
            "id": sp.id,
            "source_type": sp.source_type,
            "source_url": sp.source_url,
            "title": sp.title,
            "status": sp.status,
            "source_id": sp.source_id,
            "language": sp.language,
            "meta_json": sp.meta_json,
            "transcript_json": sp.transcript_json,
            "transcript_text": sp.transcript_text,
            "error": sp.error,
            "created_at": sp.created_at.isoformat() if sp.created_at else None,
            "updated_at": sp.updated_at.isoformat() if sp.updated_at else None,
            "playlist_id": sp.playlist_id,
            "playlist_title": sp.playlist_title,
            "playlist_index": sp.playlist_index,
        },
    }


@router.get("/{study_pack_id}/transcript")
def get_transcript(study_pack_id: int, db: Session = Depends(get_db)):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    return {
        "ok": True,
        "study_pack_id": sp.id,
        "status": sp.status,
        "source_id": sp.source_id,
        "language": sp.language,
        "transcript_text": sp.transcript_text,
        "transcript_json": sp.transcript_json,
        "updated_at": sp.updated_at.isoformat() if sp.updated_at else None,
    }


@router.get("/{study_pack_id}/transcript/chunks")
def list_transcript_chunks(
    study_pack_id: int,
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    query = db.query(TranscriptChunk).filter(TranscriptChunk.study_pack_id == study_pack_id)

    if q and q.strip():
        s = f"%{q.strip()}%"
        query = query.filter(TranscriptChunk.text.ilike(s))

    total = query.count()
    rows = (
        query.order_by(TranscriptChunk.idx.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for r in rows:
        items.append(
            {
                "id": int(r.id),
                "idx": r.idx,
                "start_sec": float(r.start_sec),
                "end_sec": float(r.end_sec),
                "text": r.text,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "updated_at": r.updated_at.isoformat() if getattr(r, "updated_at", None) else None,
            }
        )

    return {
        "ok": True,
        "study_pack_id": study_pack_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


# -----------------------
# V2.1 — KB (Embeddings)
# -----------------------
class KBEmbedRequest(BaseModel):
    model: str | None = None


class KBEmbedResponse(BaseModel):
    ok: bool
    study_pack_id: int
    job_id: int
    task_id: str
    model: str | None = None


@router.post("/{study_pack_id}/kb/embed", response_model=KBEmbedResponse)
def kb_embed(
    study_pack_id: int,
    req: KBEmbedRequest | None = None,
    db: Session = Depends(get_db),
):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    model = (req.model if req else None)
    job = create_job(db, "kb_embed_transcript_chunks", {"study_pack_id": study_pack_id, "model": model})
    async_result = embed_transcript_chunks.delay(job.id, study_pack_id, model)

    return KBEmbedResponse(ok=True, study_pack_id=study_pack_id, job_id=job.id, task_id=async_result.id, model=model)


@router.get("/{study_pack_id}/kb/status")
def kb_status(
    study_pack_id: int,
    db: Session = Depends(get_db),
    model: str | None = Query(default=None),
):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    q_chunks = db.query(func.count(TranscriptChunk.id)).filter(TranscriptChunk.study_pack_id == study_pack_id)
    total_chunks = int(q_chunks.scalar() or 0)

    q_emb = db.query(func.count(TranscriptChunkEmbedding.id)).filter(
        TranscriptChunkEmbedding.study_pack_id == study_pack_id
    )
    if model:
        q_emb = q_emb.filter(TranscriptChunkEmbedding.model == model)

    embedded = int(q_emb.scalar() or 0)

    return {"ok": True, "study_pack_id": study_pack_id, "total_chunks": total_chunks, "embedded": embedded, "model": model}


# -----------------------
# V2.2 — KB (Retrieval)
# -----------------------
class KBSearchItemModel(BaseModel):
    chunk_id: int
    idx: int
    start_sec: float
    end_sec: float
    text: str
    score: float
    distance: float


class KBSearchResponse(BaseModel):
    ok: bool
    study_pack_id: int
    model: str
    q: str
    limit: int
    hybrid: bool
    items: list[KBSearchItemModel]


@router.get("/{study_pack_id}/kb/search", response_model=KBSearchResponse)
def kb_search(
    study_pack_id: int,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    model: str = Query(default="sentence-transformers/all-MiniLM-L6-v2"),
    limit: int = Query(default=8, ge=1, le=25),
    hybrid: bool = Query(default=True),
):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    try:
        items = kb_search_chunks(
            db=db,
            study_pack_id=study_pack_id,
            q=q,
            model=model,
            limit=limit,
            hybrid=hybrid,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB search failed: {e}")

    return KBSearchResponse(
        ok=True,
        study_pack_id=study_pack_id,
        model=model,
        q=q,
        limit=limit,
        hybrid=hybrid,
        items=[KBSearchItemModel(**x) for x in items],
    )


# -----------------------
# V2.4 — KB (Q&A)
# -----------------------
class KBAskRequest(BaseModel):
    question: str

    # LLM (Ollama) model
    model: str | None = None

    # Retrieval embedding model (must match stored embeddings)
    embed_model: str | None = None

    limit: int | None = 6
    hybrid: bool | None = True
    min_best_score: float | None = 0.52


@router.post("/{study_pack_id}/kb/ask")
def kb_ask(
    study_pack_id: int,
    req: KBAskRequest,
    db: Session = Depends(get_db),
):
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Study pack not found")

    res = ask_grounded(
        db=db,
        study_pack_id=study_pack_id,
        question=req.question,
        model=req.model,
        embed_model=req.embed_model,
        limit=int(req.limit or 6),
        hybrid=bool(req.hybrid if req.hybrid is not None else True),
        min_best_score=float(req.min_best_score or 0.52),
    )

    base_url = sp.source_url or ""
    citations_out = []
    for c in (res.citations or []):
        citations_out.append(
            {
                "chunk_id": c.chunk_id,
                "idx": c.idx,
                "start_sec": c.start_sec,
                "end_sec": c.end_sec,
                "text": c.text,
                "score": c.score,
                "url": _with_timestamp(base_url, c.start_sec),  # ✅ V2.4
            }
        )

    return {
        "ok": True,
        "study_pack_id": study_pack_id,
        "refused": bool(res.refused),
        "answer": res.answer,
        "model": res.model,
        "embed_model": (req.embed_model or None),  # ✅ V2.4 (echo)
        "study_pack": {  # ✅ V2.4 convenience payload for frontend
            "id": sp.id,
            "title": sp.title,
            "source_url": sp.source_url,
            "source_type": sp.source_type,
            "playlist_id": sp.playlist_id,
            "playlist_index": sp.playlist_index,
        },
        "citations": citations_out,
        "retrieval": res.retrieval,
    }