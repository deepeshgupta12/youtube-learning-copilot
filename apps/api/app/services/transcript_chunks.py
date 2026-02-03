from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.transcript_chunk import TranscriptChunk


def segments_to_chunks(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Converts transcript segments into DB-ready chunk dicts.

    Supports both:
      A) youtube_transcript_api style: {text, start, duration}
      B) already-normalized style: {text, start_sec, end_sec}

    Returns:
      [{idx, start_sec, end_sec, text}, ...]
    """
    chunks: list[dict[str, Any]] = []
    idx = 0

    for seg in segments or []:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue

        # Case B: already normalized
        if "start_sec" in seg and "end_sec" in seg:
            start = float(seg.get("start_sec") or 0.0)
            end = float(seg.get("end_sec") or start)
        else:
            # Case A: youtube_transcript_api
            start = float(seg.get("start") or 0.0)
            dur = float(seg.get("duration") or 0.0)
            end = start + max(dur, 0.0)

        if end < start:
            end = start

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


def replace_chunks(db: Session, study_pack_id: int, chunks: list[dict[str, Any]]) -> None:
    """
    Deletes old chunks for pack and inserts new ones, then commits.
    """
    # Clear existing
    db.query(TranscriptChunk).filter(TranscriptChunk.study_pack_id == study_pack_id).delete()

    if chunks:
        rows = [
            {
                "study_pack_id": study_pack_id,
                "idx": c["idx"],
                "start_sec": c["start_sec"],
                "end_sec": c["end_sec"],
                "text": c["text"],
            }
            for c in chunks
        ]
        db.bulk_insert_mappings(TranscriptChunk, rows)

    db.commit()