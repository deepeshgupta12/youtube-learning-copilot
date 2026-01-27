from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.transcript_chunk import TranscriptChunk


def segments_to_chunks(
    segments: list[dict[str, Any]],
    *,
    target_words: int = 90,
    max_words: int = 140,
) -> list[dict[str, Any]]:
    """
    Convert fine-grained segments into chunk rows:
      {idx, start_sec, end_sec, text}

    Chunking rule:
      - accumulate segment texts until target_words reached,
        but cap at max_words.
      - chunk time range = min(start) to max(end).
    """
    chunks: list[dict[str, Any]] = []
    buf_text: list[str] = []
    buf_start: float | None = None
    buf_end: float | None = None
    buf_words = 0

    def flush():
        nonlocal buf_text, buf_start, buf_end, buf_words
        if not buf_text:
            return
        text = " ".join([t.strip() for t in buf_text if t.strip()]).strip()
        if not text:
            buf_text, buf_start, buf_end, buf_words = [], None, None, 0
            return
        chunks.append(
            {
                "idx": len(chunks),
                "start_sec": float(buf_start or 0.0),
                "end_sec": float(buf_end or (buf_start or 0.0)),
                "text": text,
            }
        )
        buf_text, buf_start, buf_end, buf_words = [], None, None, 0

    for seg in segments or []:
        txt = str(seg.get("text") or "").strip()
        if not txt:
            continue
        start = float(seg.get("start") or 0.0)
        duration = float(seg.get("duration") or 0.0)
        end = start + max(0.0, duration)

        words = len(txt.split())
        if buf_start is None:
            buf_start = start
            buf_end = end
        else:
            buf_end = max(buf_end or end, end)

        # If adding this would exceed max_words, flush first (if buffer has something)
        if buf_words > 0 and (buf_words + words) > max_words:
            flush()
            buf_start = start
            buf_end = end

        buf_text.append(txt)
        buf_words += words

        if buf_words >= target_words:
            flush()

    flush()
    return chunks


def replace_chunks(db: Session, study_pack_id: int, chunks: list[dict[str, Any]]) -> None:
    """
    Idempotent: delete existing chunks for pack, insert new ones.
    """
    db.query(TranscriptChunk).filter(TranscriptChunk.study_pack_id == study_pack_id).delete()
    for ch in chunks:
        db.add(
            TranscriptChunk(
                study_pack_id=study_pack_id,
                idx=int(ch["idx"]),
                start_sec=float(ch["start_sec"]),
                end_sec=float(ch["end_sec"]),
                text=str(ch["text"]),
            )
        )
    db.commit()