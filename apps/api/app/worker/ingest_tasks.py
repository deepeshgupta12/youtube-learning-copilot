from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.study_pack import StudyPack
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


@celery_app.task(name="ingest.youtube_playlist")
def ingest_youtube_playlist(
    job_id: int,
    playlist_id: str,
    study_pack_ids: list[int],
    language: str | None = None,
) -> dict:
    """
    V1 playlist ingestion:
    - study_pack rows are created in API (so we have ids immediately)
    - worker ingests captions sequentially for each pack
    """
    db: Session = SessionLocal()
    failed: list[dict] = []
    done: int = 0

    try:
        set_job_status(db, job_id, "running")

        for sp_id in study_pack_ids:
            sp = db.query(StudyPack).filter(StudyPack.id == sp_id).first()
            if not sp:
                failed.append({"study_pack_id": sp_id, "error": "StudyPack not found"})
                continue

            video_id = sp.source_id
            if not video_id:
                failed.append({"study_pack_id": sp_id, "error": "Missing source_id/video_id"})
                continue

            try:
                t = transcript.fetch_youtube_transcript(video_id, language=language)
                meta = {"video_id": video_id, "provider": "youtube", "captions": True, "playlist_id": playlist_id}

                set_ingested(
                    db,
                    sp_id,
                    title=sp.title,  # keep whatever we set at creation time
                    meta=meta,
                    transcript_segments=t["segments"],
                    transcript_text=t["text"],
                    language=t.get("language") or language,
                )
                done += 1
            except transcript.TranscriptNotFound as e:
                set_failed(db, sp_id, str(e))
                failed.append({"study_pack_id": sp_id, "error": str(e)})
            except Exception as e:
                set_failed(db, sp_id, str(e))
                failed.append({"study_pack_id": sp_id, "error": str(e)})

        if failed:
            set_job_status(db, job_id, "failed", error=f"{len(failed)} pack(s) failed in playlist ingestion.")
        else:
            set_job_status(db, job_id, "done")

        return {
            "ok": len(failed) == 0,
            "job_id": job_id,
            "playlist_id": playlist_id,
            "total": len(study_pack_ids),
            "done": done,
            "failed": failed,
        }
    finally:
        db.close()