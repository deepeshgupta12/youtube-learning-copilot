from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.jobs import set_job_status
from app.services.study_packs import set_ingested, set_failed
import app.services.transcript as transcript
from app.worker.celery_app import celery_app


@celery_app.task(name="ingest.youtube_captions")
def ingest_youtube_captions(job_id: int, study_pack_id: int, video_id: str, language: str | None = None) -> dict:
    db: Session = SessionLocal()
    try:
        set_job_status(db, job_id, "running")

        t = transcript.fetch_youtube_transcript(video_id, language=language)

        # minimal meta for V0
        meta = {"video_id": video_id, "provider": "youtube", "captions": True}

        set_ingested(
            db,
            study_pack_id,
            title=None,
            meta=meta,
            transcript_segments=t["segments"],
            transcript_text=t["text"],
            language=t.get("language") or language,
        )

        set_job_status(db, job_id, "done")
        return {"ok": True, "study_pack_id": study_pack_id, "job_id": job_id}
    except transcript.TranscriptNotFound as e:
        set_failed(db, study_pack_id, str(e))
        set_job_status(db, job_id, "failed", error=str(e))
        raise
    except Exception as e:
        set_failed(db, study_pack_id, str(e))
        set_job_status(db, job_id, "failed", error=str(e))
        raise
    finally:
        db.close()
