from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.chapter_progress import ChapterProgress
from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_chapters(db: Session, study_pack_id: int) -> list[dict[str, Any]]:
    """
    Returns the chapters items array from StudyMaterial(kind="chapters").
    Expected shape:
      {"items":[{"title":"...","summary":"...","sentences":[...]}], "_meta": {...}}
    """
    row = (
        db.query(StudyMaterial)
        .filter(StudyMaterial.study_pack_id == study_pack_id, StudyMaterial.kind == "chapters")
        .first()
    )
    if not row or not row.content_json:
        return []

    try:
        payload = json.loads(row.content_json)
    except Exception:
        return []

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        summary = str(it.get("summary") or "").strip()
        sentences = it.get("sentences")
        if not isinstance(sentences, list):
            sentences = []
        # Keep only string sentences
        sentences = [str(s) for s in sentences if isinstance(s, (str, int, float))]

        # include even if some fields empty, as long as something exists
        if title or summary or sentences:
            out.append(
                {
                    "title": title,
                    "summary": summary,
                    "sentences": sentences,
                }
            )
    return out


def get_chapters_progress(db: Session, study_pack_id: int) -> dict[str, Any]:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise ValueError("Study pack not found")

    chapters = _load_chapters(db, study_pack_id)
    total = len(chapters)

    rows = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.study_pack_id == study_pack_id)
        .all()
    )
    by_idx = {r.chapter_index: r for r in rows}

    items: list[dict[str, Any]] = []
    opened = 0
    completed = 0

    # Build items summary for UI
    for i in range(total):
        r = by_idx.get(i)
        status = r.status if r else None
        opened_count = int(r.opened_count or 0) if r else 0
        completed_count = int(r.completed_count or 0) if r else 0

        if opened_count > 0:
            opened += 1
        if status == "completed":
            completed += 1

        items.append(
            {
                "chapter_index": i,
                "status": status,
                "opened_count": opened_count,
                "completed_count": completed_count,
                "last_opened_at": (r.last_opened_at.isoformat() if (r and r.last_opened_at) else None),
                "last_completed_at": (r.last_completed_at.isoformat() if (r and r.last_completed_at) else None),
            }
        )

    # Resume logic:
    # 1) last opened chapter that isn't completed (max last_opened_at)
    # 2) else first not completed
    # 3) else 0
    resume_index = 0
    candidates = [r for r in rows if (r and r.last_opened_at and r.status != "completed")]
    if candidates:
        candidates.sort(key=lambda x: x.last_opened_at or _now(), reverse=True)
        resume_index = int(candidates[0].chapter_index)
    else:
        # find first not completed among total
        for i in range(total):
            r = by_idx.get(i)
            if not r or r.status != "completed":
                resume_index = i
                break

    return {
        "study_pack_id": study_pack_id,
        "total_chapters": total,
        "opened_chapters": opened,
        "completed_chapters": completed,
        "resume_chapter_index": resume_index if total > 0 else 0,
        "items": items,
    }


def mark_chapter(
    db: Session,
    study_pack_id: int,
    chapter_index: int,
    action: str,
) -> dict[str, Any]:
    """
    action:
      - "open"       -> increments opened_count, status becomes in_progress (unless already completed)
      - "complete"   -> increments completed_count, status becomes completed
      - "reset"      -> clears status (keeps counters)
    """
    if chapter_index < 0:
        raise ValueError("chapter_index must be >= 0")

    chapters = _load_chapters(db, study_pack_id)
    if not chapters:
        raise ValueError("No chapters found for this pack. Generate materials first.")
    if chapter_index >= len(chapters):
        raise ValueError(f"chapter_index out of range (0..{len(chapters)-1})")

    row = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.study_pack_id == study_pack_id,
            ChapterProgress.chapter_index == chapter_index,
        )
        .first()
    )
    if not row:
        row = ChapterProgress(study_pack_id=study_pack_id, chapter_index=chapter_index)
        db.add(row)

    now = _now()

    if action == "open":
        row.opened_count = int(row.opened_count or 0) + 1
        row.last_opened_at = now
        # Don't downgrade completed to in_progress
        if row.status != "completed":
            row.status = "in_progress"

    elif action == "complete":
        row.opened_count = int(row.opened_count or 0) + 1
        row.last_opened_at = now
        row.completed_count = int(row.completed_count or 0) + 1
        row.last_completed_at = now
        row.status = "completed"

    elif action == "reset":
        row.opened_count = int(row.opened_count or 0) + 1
        row.last_opened_at = now
        row.status = None

    else:
        raise ValueError("Invalid action. Use one of: open, complete, reset")

    db.commit()
    db.refresh(row)
    return get_chapters_progress(db, study_pack_id)