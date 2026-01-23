from apps.api.app.models.study_pack import StudyPack
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.jobs import create_job
from app.services.study_packs import create_study_pack
from app.services.youtube import extract_youtube_video_id
from app.worker.ingest_tasks import ingest_youtube_captions

router = APIRouter(prefix="/study-packs", tags=["study_packs"])


class StudyPackFromYoutubeRequest(BaseModel):
    url: str
    language: str | None = None


class StudyPackFromYoutubeResponse(BaseModel):
    ok: bool
    study_pack_id: int
    job_id: int
    task_id: str
    video_id: str


@router.post("/from-youtube", response_model=StudyPackFromYoutubeResponse)
def create_from_youtube(req: StudyPackFromYoutubeRequest, db: Session = Depends(get_db)) -> StudyPackFromYoutubeResponse:
    video_id = extract_youtube_video_id(req.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    sp = create_study_pack(
        db,
        source_type="youtube_video",
        source_url=req.url,
        source_id=video_id,
        language=req.language,
    )

    job = create_job(db, "ingest_youtube_captions", {"study_pack_id": sp.id, "video_id": video_id})

    async_result = ingest_youtube_captions.delay(job.id, sp.id, video_id, req.language)

    return StudyPackFromYoutubeResponse(
        ok=True,
        study_pack_id=sp.id,
        job_id=job.id,
        task_id=async_result.id,
        video_id=video_id,
    )

@router.get("/study-packs/{study_pack_id}")
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
        },
    }
