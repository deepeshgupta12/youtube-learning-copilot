from __future__ import annotations

import os
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.study_pack import StudyPack
from app.services.jobs import set_job_status
from app.services.study_packs import set_ingested, set_failed
import app.services.transcript as transcript
from app.worker.celery_app import celery_app

# V1.1: STT fallback + chunk store
from app.core.youtube_settings import youtube_settings
from app.services.youtube_audio import download_youtube_audio, AudioDownloadError
from app.services.audio_utils import normalize_to_wav_16k_mono, AudioNormalizeError
from app.services.stt import transcribe_faster_whisper, STTError
from app.services.transcript_chunks import segments_to_chunks, replace_chunks


def _ingest_one_video_with_fallback(
    db: Session,
    *,
    study_pack_id: int,
    video_id: str,
    language: str | None,
    base_meta: dict | None = None,
    title: str | None = None,
) -> None:
    """
    Captions-first ingestion; if captions missing, fallback to:
      yt-dlp audio -> ffmpeg normalize -> faster-whisper STT

    Always:
      - set_ingested(...)
      - write transcript_chunks rows for citations/jump-to-time
    """
    provider = "youtube"
    captions_used = True
    stt_used = False
    stt_model = None

    t = None

    # 1) Captions-first
    try:
        t = transcript.fetch_youtube_transcript(video_id, language=language)
    except transcript.TranscriptNotFound:
        # 2) STT fallback
        captions_used = False
        stt_used = True
        provider = "stt"

        model_size = os.getenv("STT_MODEL_SIZE", "small")
        compute_type = os.getenv("STT_COMPUTE_TYPE", "int8")
        stt_model = f"faster-whisper:{model_size}:{compute_type}"

        audio_path = None
        wav_path = None
        try:
            audio_path = download_youtube_audio(
                video_id,
                cookies_file=youtube_settings.cookies_file,
                proxy_url=youtube_settings.proxy_url,
            )
            wav_path = normalize_to_wav_16k_mono(audio_path)
            t = transcribe_faster_whisper(
                wav_path,
                language=language,
                model_size=model_size,
                compute_type=compute_type,
            )
        except (AudioDownloadError, AudioNormalizeError, STTError) as e:
            # bubble up as TranscriptNotFound so existing error handling stays consistent
            raise transcript.TranscriptNotFound(str(e)) from e
        finally:
            # cleanup tempdirs created in helpers
            if wav_path is not None and hasattr(wav_path, "_tmp"):
                try:
                    wav_path._tmp.cleanup()  # type: ignore[attr-defined]
                except Exception:
                    pass
            if audio_path is not None and hasattr(audio_path, "_tmp"):
                try:
                    audio_path._tmp.cleanup()  # type: ignore[attr-defined]
                except Exception:
                    pass

    meta = {
        **(base_meta or {}),
        "video_id": video_id,
        "provider": provider,
        "captions": captions_used,
        "stt": stt_used,
        "stt_model": stt_model,
    }

    # Persist transcript on study_packs
    set_ingested(
        db,
        study_pack_id,
        title=title,
        meta=meta,
        transcript_segments=t["segments"],
        transcript_text=t["text"],
        language=t.get("language") or language,
    )

    # Persist timestamped chunks on transcript_chunks
    chunks = segments_to_chunks(t["segments"])
    replace_chunks(db, study_pack_id, chunks)


@celery_app.task(name="ingest.youtube_captions")
def ingest_youtube_captions(
    job_id: int,
    study_pack_id: int,
    video_id: str,
    language: str | None = None,
) -> dict:
    db: Session = SessionLocal()
    try:
        set_job_status(db, job_id, "running")

        _ingest_one_video_with_fallback(
            db,
            study_pack_id=study_pack_id,
            video_id=video_id,
            language=language,
            base_meta=None,
            title=None,
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
    - captions-first, STT fallback per video
    - always stores transcript_chunks (timestamps)
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
                msg = "Missing source_id/video_id"
                set_failed(db, sp_id, msg)
                failed.append({"study_pack_id": sp_id, "error": msg})
                continue

            try:
                _ingest_one_video_with_fallback(
                    db,
                    study_pack_id=sp_id,
                    video_id=video_id,
                    language=language,
                    base_meta={"playlist_id": playlist_id},
                    title=sp.title,
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