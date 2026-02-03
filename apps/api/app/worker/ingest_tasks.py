# apps/api/app/worker/ingest_tasks.py
from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.study_pack import StudyPack
from app.models.transcript_chunk import TranscriptChunk
from app.services.jobs import merge_job_payload, set_job_status
from app.services.study_packs import set_failed, set_ingested
import app.services.transcript as transcript
from app.worker.celery_app import celery_app


# -----------------------------
# Smart chunking (V1.4.2)
#   - time/char bound chunks
#   - overlap-aware append to reduce repetition
# -----------------------------
_CHUNK_MAX_SECONDS = float(os.getenv("YLC_CHUNK_MAX_SECONDS", "35"))
_CHUNK_MAX_CHARS = int(os.getenv("YLC_CHUNK_MAX_CHARS", "900"))
_CHUNK_MIN_CHARS = int(os.getenv("YLC_CHUNK_MIN_CHARS", "220"))

# Overlap detection knobs (word-based)
_OVERLAP_WINDOW_WORDS = int(os.getenv("YLC_OVERLAP_WINDOW_WORDS", "18"))  # how many words to compare
_OVERLAP_MIN_WORDS = int(os.getenv("YLC_OVERLAP_MIN_WORDS", "4"))  # require at least this many words overlap


def _seg_end(seg: dict[str, Any]) -> float:
    start = float(seg.get("start") or 0.0)
    dur = float(seg.get("duration") or 0.0)
    return float(max(start, start + max(0.0, dur)))


def _normalize_spaces(s: str) -> str:
    return " ".join((s or "").split()).strip()


_word_re = re.compile(r"[A-Za-z0-9']+")


def _words(s: str) -> list[str]:
    """
    Lowercased word tokens.
    Using regex helps avoid punctuation mismatches from captions/subs.
    """
    if not s:
        return []
    return [w.lower() for w in _word_re.findall(s)]


def _strip_overlap(existing_text: str, incoming_text: str) -> str:
    """
    Remove duplicated overlap where incoming starts with something existing already ends with.

    Example:
      existing: "... talk about the brain"
      incoming: "talk about the brain structure and function"
      => returns "structure and function"
    """
    a = _words(existing_text)
    b = _words(incoming_text)
    if not a or not b:
        return incoming_text.strip()

    # Compare suffix of a vs prefix of b, up to window size
    win = min(_OVERLAP_WINDOW_WORDS, len(a), len(b))
    best_k = 0
    for k in range(win, _OVERLAP_MIN_WORDS - 1, -1):
        if a[-k:] == b[:k]:
            best_k = k
            break

    if best_k <= 0:
        return incoming_text.strip()

    # We found overlap by words; now remove the overlapped prefix from the *original* incoming text.
    # Safer approach: drop by word count from the incoming string while preserving casing/punctuation.
    # We'll split incoming by whitespace and remove the first `best_k` "word-like" tokens.
    tokens = incoming_text.strip().split()
    if not tokens:
        return incoming_text.strip()

    # Build mapping of which whitespace tokens contain word tokens.
    # We remove tokens until we've removed best_k word tokens.
    removed_word_count = 0
    cut_idx = 0
    for i, tok in enumerate(tokens):
        # Count how many word tokens in this whitespace token
        wcount = len(_word_re.findall(tok))
        if wcount > 0:
            removed_word_count += wcount
        cut_idx = i + 1
        if removed_word_count >= best_k:
            break

    remainder = " ".join(tokens[cut_idx:]).strip()
    return remainder


def _join_text(parts: list[str]) -> str:
    s = " ".join([p.strip() for p in parts if (p or "").strip()]).strip()
    return _normalize_spaces(s)


def _append_segment_text(cur_text_parts: list[str], seg_text: str) -> None:
    """
    Append seg_text into cur_text_parts but avoid overlap duplication.
    """
    seg_text = _normalize_spaces(seg_text)
    if not seg_text:
        return

    if not cur_text_parts:
        cur_text_parts.append(seg_text)
        return

    existing = _join_text(cur_text_parts)
    remainder = _strip_overlap(existing, seg_text)
    remainder = _normalize_spaces(remainder)

    # If remainder became empty, don't append anything
    if remainder:
        cur_text_parts.append(remainder)


def _segments_to_smart_chunks(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build fewer, higher-quality chunks from cleaned segments.

    Input segments schema:
      {text, start, duration}

    Output chunks schema:
      {idx, start_sec, end_sec, text}
    """
    if not segments:

        chunks: list[dict[str, Any]] = []
        idx = 0

    cur_text_parts: list[str] = []
    cur_start: float | None = None
    cur_end: float | None = None

    def flush(force: bool = False):
        nonlocal idx, cur_text_parts, cur_start, cur_end
        if cur_start is None or cur_end is None:
            cur_text_parts = []
            cur_start = None
            cur_end = None
            return

        text = _join_text(cur_text_parts)
        if not text:
            cur_text_parts = []
            cur_start = None
            cur_end = None
            return

        # avoid too many tiny chunks unless forced
        if not force and len(text) < _CHUNK_MIN_CHARS and chunks:
            prev = chunks[-1]
            prev["text"] = _join_text([prev["text"], text])
            prev["end_sec"] = max(float(prev["end_sec"]), float(cur_end))
        else:
            chunks.append(
                {
                    "idx": idx,
                    "start_sec": float(cur_start),
                    "end_sec": float(cur_end),
                    "text": text,
                }
            )
            idx += 1

        cur_text_parts = []
        cur_start = None
        cur_end = None

    for seg in segments:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue

        start = float(seg.get("start") or 0.0)
        end = _seg_end(seg)

        if cur_start is None:
            cur_start = start
            cur_end = end
            cur_text_parts = []
            _append_segment_text(cur_text_parts, txt)
            continue

        # evaluate if adding this segment would exceed chunk constraints
        # NOTE: use overlap-aware append for length estimation too
        existing = _join_text(cur_text_parts)
        candidate_remainder = _strip_overlap(existing, txt)
        candidate_text = _join_text(cur_text_parts + ([candidate_remainder] if candidate_remainder else []))

        next_end = max(float(cur_end), end)
        next_text_len = len(candidate_text)
        next_dur = next_end - float(cur_start)

        if next_text_len > _CHUNK_MAX_CHARS or next_dur > _CHUNK_MAX_SECONDS:
            flush(force=True)
            # start new chunk with current seg
            cur_start = start
            cur_end = end
            cur_text_parts = []
            _append_segment_text(cur_text_parts, txt)
            continue

        # append with overlap-dedupe
        _append_segment_text(cur_text_parts, txt)
        cur_end = next_end

    flush(force=True)
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
      - stores cleaned transcript_json + cleaned transcript_text
      - writes smart transcript_chunks (V1.4.2 overlap-aware)
    """
    db: Session = SessionLocal()
    try:
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

        t = transcript.fetch_youtube_transcript(video_id, language=language)
        method = t.get("method") or "unknown"

        raw_segments = t["segments"]
        merge_job_payload(db, job_id, {"method": method, "progress": {"stage": "clean_transcript"}})

        cleaned_segments = transcript.clean_segments(raw_segments)
        cleaned_text = transcript._segments_to_text(cleaned_segments)

        merge_job_payload(db, job_id, {"progress": {"stage": "write_chunks"}})

        chunks = _segments_to_smart_chunks(cleaned_segments)
        chunks_written = _replace_transcript_chunks(db, study_pack_id, chunks)

        meta = {
            "video_id": video_id,
            "provider": "youtube",
            "method": method,
            "captions": method == "captions",
            "ytdlp_subs": method == "ytdlp_subs",
            "stt": method == "stt",
            "raw_segments": len(raw_segments or []),
            "cleaned_segments": len(cleaned_segments or []),
            "chunks_written": chunks_written,
            "chunking": {
                "max_seconds": _CHUNK_MAX_SECONDS,
                "max_chars": _CHUNK_MAX_CHARS,
                "min_chars": _CHUNK_MIN_CHARS,
                "overlap_window_words": _OVERLAP_WINDOW_WORDS,
                "overlap_min_words": _OVERLAP_MIN_WORDS,
            },
        }

        set_ingested(
            db,
            study_pack_id,
            title=None,
            meta=meta,
            transcript_segments=cleaned_segments,
            transcript_text=cleaned_text,
            language=t.get("language") or language,
        )

        merge_job_payload(db, job_id, {"chunks_written": chunks_written, "progress": {"stage": "done"}})
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
            merge_job_payload(db, job_id, {"progress": {"stage": "ingesting", "done": i - 1, "total": total}})

            sp = db.query(StudyPack).filter(StudyPack.id == sp_id).first()
            if not sp:
                failed.append({"study_pack_id": sp_id, "error": "StudyPack not found"})
                continue

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

                raw_segments = t["segments"]
                cleaned_segments = transcript.clean_segments(raw_segments)
                cleaned_text = transcript._segments_to_text(cleaned_segments)

                chunks = _segments_to_smart_chunks(cleaned_segments)
                chunks_written = _replace_transcript_chunks(db, sp_id, chunks)

                meta = {
                    "video_id": video_id,
                    "provider": "youtube",
                    "playlist_id": playlist_id,
                    "method": method,
                    "captions": method == "captions",
                    "ytdlp_subs": method == "ytdlp_subs",
                    "stt": method == "stt",
                    "raw_segments": len(raw_segments or []),
                    "cleaned_segments": len(cleaned_segments or []),
                    "chunks_written": chunks_written,
                    "chunking": {
                        "max_seconds": _CHUNK_MAX_SECONDS,
                        "max_chars": _CHUNK_MAX_CHARS,
                        "min_chars": _CHUNK_MIN_CHARS,
                        "overlap_window_words": _OVERLAP_WINDOW_WORDS,
                        "overlap_min_words": _OVERLAP_MIN_WORDS,
                    },
                }

                set_ingested(
                    db,
                    sp_id,
                    title=sp.title,
                    meta=meta,
                    transcript_segments=cleaned_segments,
                    transcript_text=cleaned_text,
                    language=t.get("language") or language,
                )
                done += 1

            except transcript.TranscriptNotFound as e:
                set_failed(db, sp_id, str(e))
                failed.append({"study_pack_id": sp_id, "error": str(e)})
            except Exception as e:
                set_failed(db, sp_id, str(e))
                failed.append({"study_pack_id": sp_id, "error": str(e)})

            merge_job_payload(db, job_id, {"progress": {"stage": "ingesting", "done": i, "total": total}})

        summary = {
            "playlist_id": playlist_id,
            "total": total,
            "ingested": done,
            "failed_count": len(failed),
            "failed": failed[:200],
        }

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