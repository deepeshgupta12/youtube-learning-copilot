# apps/api/app/worker/ingest_tasks.py
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.study_pack import StudyPack
from app.models.transcript_chunk import TranscriptChunk
from app.services.jobs import set_job_status, merge_job_payload
from app.services.study_packs import set_ingested, set_failed
import app.services.transcript as transcript
from app.worker.celery_app import celery_app


def _segments_to_chunks(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize transcript segments into canonical chunk rows:
      {idx, start_sec, end_sec, text}

    Supports segments that look like:
      - youtube_transcript_api: {text, start, duration}
      - our vtt parser:         {text, start, duration}
      - STT:                    {text, start, duration}
    """
    chunks: list[dict[str, Any]] = []
    idx = 0

    for seg in segments or []:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue

        start = float(seg.get("start") or 0.0)
        duration = float(seg.get("duration") or 0.0)
        end = float(max(start, start + max(0.0, duration)))

        chunks.append(
            {
                "idx": idx,
                "start_sec": start,
                "end_sec": end,
                "text": txt,
            }
        )
        idx += 1

    return chunks


def _replace_transcript_chunks(db: Session, study_pack_id: int, chunks: list[dict[str, Any]]) -> int:
    """
    Replace all chunks for a pack (idempotent).
    """
    db.query(TranscriptChunk).filter(TranscriptChunk.study_pack_id == study_pack_id).delete()

    if not chunks:
        db.commit()
        return 0

    rows = [
        TranscriptChunk(
            study_pack_id=study_pack_id,
            idx=c["idx"],
            start_sec=c["start_sec"],
            end_sec=c["end_sec"],
            text=c["text"],
        )
        for c in chunks
    ]
    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


@celery_app.task(name="ingest.youtube_captions")
def ingest_youtube_captions(job_id: int, study_pack_id: int, video_id: str, language: str | None = None) -> dict:
    """
    V1 ingestion (single video):
      - captions-first
      - yt-dlp subs fallback
      - STT fallback (audio+ffmpeg+faster-whisper)
      - always stores timestamped transcript_json
      - always writes transcript_chunks
    """
    db: Session = SessionLocal()
    try:
        # 1) Mark job running + seed payload
        set_job_status(db, job_id, "running")
        merge_job_payload(
            db,
            job_id,
            {
                "study_pack_id": study_pack_id,
                "video_id": video_id,
                "progress": {"stage": "fetch_transcript"},
            },
        )

        # 2) Fetch transcript (captions -> ytdlp -> stt handled inside service)
        t = transcript.fetch_youtube_transcript(video_id, language=language)

        method = t.get("method") or "unknown"
        segments = t["segments"]
        text = t["text"]

        merge_job_payload(
            db,
            job_id,
            {
                "method": method,
                "progress": {"stage": "write_chunks"},
            },
        )

        # 3) Write chunks
        chunks = _segments_to_chunks(segments)
        chunks_written = _replace_transcript_chunks(db, study_pack_id, chunks)

        # 4) Mark study pack ingested
        meta = {
            "video_id": video_id,
            "provider": "youtube",
            "method": method,
            "captions": method == "captions",
            "ytdlp_subs": method == "ytdlp_subs",
            "stt": method == "stt",
            "chunks_written": chunks_written,
        }

        set_ingested(
            db,
            study_pack_id,
            title=None,
            meta=meta,
            transcript_segments=segments,  # IMPORTANT: store timestamp segments (not plain text)
            transcript_text=text,
            language=t.get("language") or language,
        )

        merge_job_payload(
            db,
            job_id,
            {
                "chunks_written": chunks_written,
                "progress": {"stage": "done"},
            },
        )

        set_job_status(db, job_id, "done")
        return {
            "ok": True,
            "study_pack_id": study_pack_id,
            "job_id": job_id,
            "method": method,
            "chunks_written": chunks_written,
        }

    except transcript.TranscriptNotFound as e:
        err = str(e)
        set_failed(db, study_pack_id, err)
        merge_job_payload(db, job_id, {"progress": {"stage": "failed"}, "error": err})
        set_job_status(db, job_id, "failed", error=err)
        # keep raise to show proper celery failure semantics for "not found"
        raise
    except Exception as e:
        err = str(e)
        set_failed(db, study_pack_id, err)
        merge_job_payload(db, job_id, {"progress": {"stage": "failed"}, "error": err})
        set_job_status(db, job_id, "failed", error=err)
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
      - worker ingests each pack sequentially
      - Private/Deleted videos are expected to fail; job should still be "done"
      - Job payload_json should carry summary (ingested/failed + failures list)
    """
    db: Session = SessionLocal()
    failed: list[dict[str, Any]] = []
    done: int = 0
    total = len(study_pack_ids)

    try:
        set_job_status(db, job_id, "running")
        merge_job_payload(
            db,
            job_id,
            {
                "playlist_id": playlist_id,
                "progress": {"stage": "start", "done": 0, "total": total},
            },
        )

        for i, sp_id in enumerate(study_pack_ids, start=1):
            # Update progress every item (lightweight)
            merge_job_payload(db, job_id, {"progress": {"stage": "ingesting", "done": i - 1, "total": total}})

            sp = db.query(StudyPack).filter(StudyPack.id == sp_id).first()
            if not sp:
                failed.append({"study_pack_id": sp_id, "error": "StudyPack not found"})
                continue

            # Skip fast-known invalids based on title assigned during playlist discovery
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
                t = transcript.fetch_youtube_transcript(video_id, language=language)
                method = t.get("method") or "unknown"
                segments = t["segments"]
                text = t["text"]

                chunks = _segments_to_chunks(segments)
                chunks_written = _replace_transcript_chunks(db, sp_id, chunks)

                meta = {
                    "video_id": video_id,
                    "provider": "youtube",
                    "playlist_id": playlist_id,
                    "method": method,
                    "captions": method == "captions",
                    "ytdlp_subs": method == "ytdlp_subs",
                    "stt": method == "stt",
                    "chunks_written": chunks_written,
                }

                set_ingested(
                    db,
                    sp_id,
                    title=sp.title,
                    meta=meta,
                    transcript_segments=segments,
                    transcript_text=text,
                    language=t.get("language") or language,
                )
                done += 1

            except transcript.TranscriptNotFound as e:
                set_failed(db, sp_id, str(e))
                failed.append({"study_pack_id": sp_id, "error": str(e)})
            except Exception as e:
                set_failed(db, sp_id, str(e))
                failed.append({"study_pack_id": sp_id, "error": str(e)})

            # Keep progress moving
            merge_job_payload(db, job_id, {"progress": {"stage": "ingesting", "done": i, "total": total}})

        summary = {
            "playlist_id": playlist_id,
            "total": total,
            "ingested": done,
            "failed_count": len(failed),
            "failed": failed[:200],  # cap to avoid huge job payloads
        }

        # IMPORTANT: job is "done" even if partial failures
        msg = None
        if failed:
            msg = f"done_with_errors: failed={len(failed)}/{total}"

        merge_job_payload(db, job_id, {"summary": summary, "progress": {"stage": "done", "done": total, "total": total}})
        set_job_status(db, job_id, "done", error=msg)

        return {"ok": True, "job_id": job_id, **summary}

    except Exception as e:
        err = str(e)
        merge_job_payload(db, job_id, {"progress": {"stage": "failed"}, "error": err})
        set_job_status(db, job_id, "failed", error=err)
        raise
    finally:
        db.close()