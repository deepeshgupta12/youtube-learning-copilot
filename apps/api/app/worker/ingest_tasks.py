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

            # Fail-fast: yt-dlp marks these as [Private video] / [Deleted video]
            if (sp.title or "").strip().lower() in ["[private video]", "[deleted video]"]:
                msg = f"{sp.title} (skipped)"
                set_failed(db, sp_id, msg)
                failed.append({"study_pack_id": sp_id, "error": msg})
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
                    title=sp.title,
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

        # Terminalize job as DONE always; store summary in error field if needed
        summary = f"playlist ingestion finished: total={len(study_pack_ids)}, ingested={done}, failed={len(failed)}"
        if failed:
            set_job_status(db, job_id, "done", error=summary)
        else:
            set_job_status(db, job_id, "done", error=None)

        return {
            "ok": True,  # job completed (not “all succeeded”)
            "job_id": job_id,
            "playlist_id": playlist_id,
            "total": len(study_pack_ids),
            "ingested": done,
            "failed_count": len(failed),
            "failed": failed,
        }
    finally:
        db.close()