from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

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

router = APIRouter(prefix="/study-packs", tags=["study_packs"])


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

    # extra playlist info (backward compatible)
    playlist_pack_ids: list[int] | None = None
    playlist_created_count: int | None = None
    playlist_reused_count: int | None = None


@router.get("")
def list_study_packs(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    playlist_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    V1 Minimal Library:
    - Recent study packs
    - Search by title/url/id/playlist fields
    - Optional filters (status, source_type, playlist_id)
    - Pagination via limit/offset
    """
    query = db.query(StudyPack)

    if status:
        query = query.filter(StudyPack.status == status)

    if source_type:
        query = query.filter(StudyPack.source_type == source_type)

    if playlist_id:
        query = query.filter(StudyPack.playlist_id == playlist_id)

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

    return {
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "packs": packs,
    }


@router.post("/from-youtube", response_model=StudyPackFromYoutubeResponse)
def create_from_youtube(req: StudyPackFromYoutubeRequest, db: Session = Depends(get_db)) -> StudyPackFromYoutubeResponse:
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    language = (req.language or "").strip() or None

    # 1) Single video
    video_id = extract_youtube_video_id(url)
    if video_id:
        # Reuse if already exists (idempotent-ish)
        existing = (
            db.query(StudyPack)
            .filter(
                and_(
                    StudyPack.source_type == "youtube_video",
                    StudyPack.source_id == video_id,
                    StudyPack.playlist_id.is_(None),
                )
            )
            .order_by(StudyPack.created_at.desc())
            .first()
        )

        if existing:
            sp = existing
            # update url/language if needed
            if url and sp.source_url != url:
                sp.source_url = url
            if language and not sp.language:
                sp.language = language
            db.commit()
            db.refresh(sp)
        else:
            sp = create_study_pack(
                db,
                source_type="youtube_video",
                source_url=url,
                source_id=video_id,
                language=language,
            )

        job = create_job(db, "ingest_youtube_captions", {"study_pack_id": sp.id, "video_id": video_id})
        async_result = ingest_youtube_captions.delay(job.id, sp.id, video_id, language)

        return StudyPackFromYoutubeResponse(
            ok=True,
            study_pack_id=sp.id,
            job_id=job.id,
            task_id=async_result.id,
            video_id=video_id,
        )

    # 2) Playlist
    playlist_id = extract_youtube_playlist_id(url)
    if not playlist_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL (not a video or playlist)")

    meta = fetch_playlist_metadata(url, max_items=200)
    playlist_title = meta.get("playlist_title")
    entries = meta.get("entries") or []

    if not entries:
        raise HTTPException(status_code=400, detail="Playlist has no usable video entries")

    created_ids: list[int] = []
    reused_ids: list[int] = []

    # Create (or reuse) packs first, commit once
    for e in entries:
        vid = e["video_id"]
        idx = e["index"]
        title = e.get("title")

        # Reuse if same video already exists under same playlist_id
        existing = (
            db.query(StudyPack)
            .filter(
                and_(
                    StudyPack.source_type == "youtube_video",
                    StudyPack.source_id == vid,
                    StudyPack.playlist_id == playlist_id,
                )
            )
            .order_by(StudyPack.created_at.desc())
            .first()
        )

        if existing:
            sp = existing
            reused_ids.append(sp.id)
            # keep pack url aligned to playlist context
            desired_url = build_video_url(vid, playlist_id=playlist_id, playlist_index=idx)
            if desired_url and sp.source_url != desired_url:
                sp.source_url = desired_url
            if language and not sp.language:
                sp.language = language
            if playlist_title and not sp.playlist_title:
                sp.playlist_title = playlist_title
            if sp.playlist_index is None:
                sp.playlist_index = idx
            if title and not sp.title:
                sp.title = title
            continue

        sp = create_study_pack(
            db,
            source_type="youtube_video",
            source_url=build_video_url(vid, playlist_id=playlist_id, playlist_index=idx),
            source_id=vid,
            language=language,
        )

        sp.playlist_id = playlist_id
        sp.playlist_title = playlist_title
        sp.playlist_index = idx
        if title and not sp.title:
            sp.title = title

        created_ids.append(sp.id)

    db.commit()

    all_ids = reused_ids + created_ids
    if not all_ids:
        raise HTTPException(status_code=400, detail="Playlist has no usable video entries")

    job = create_job(
        db,
        "ingest_youtube_playlist",
        {"playlist_id": playlist_id, "study_pack_ids": all_ids, "url": url},
    )
    async_result = ingest_youtube_playlist.delay(job.id, playlist_id, all_ids, language)

    # Return the first pack id so current UI can auto-open /packs/:id
    return StudyPackFromYoutubeResponse(
        ok=True,
        study_pack_id=all_ids[0],
        job_id=job.id,
        task_id=async_result.id,
        video_id=None,
        playlist_id=playlist_id,
        playlist_title=playlist_title,
        playlist_count=len(all_ids),
        playlist_pack_ids=all_ids,
        playlist_created_count=len(created_ids),
        playlist_reused_count=len(reused_ids),
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