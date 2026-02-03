from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack
from app.models.flashcard_progress import FlashcardProgress


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_flashcards(db: Session, study_pack_id: int) -> list[dict[str, Any]]:
    """
    Returns the flashcards items array from StudyMaterial(kind="flashcards").
    Expected shape:
      {"items":[{"q":"...","a":"..."}, ...], "_meta": {...}}
    """
    row = (
        db.query(StudyMaterial)
        .filter(StudyMaterial.study_pack_id == study_pack_id, StudyMaterial.kind == "flashcards")
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
        if isinstance(it, dict) and (it.get("q") or it.get("a")):
            out.append({"q": it.get("q") or "", "a": it.get("a") or ""})
    return out


def get_flashcards_progress(db: Session, study_pack_id: int) -> dict[str, Any]:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise ValueError("Study pack not found")

    cards = _load_flashcards(db, study_pack_id)
    total = len(cards)

    rows = (
        db.query(FlashcardProgress)
        .filter(FlashcardProgress.study_pack_id == study_pack_id)
        .all()
    )
    by_idx = {r.card_index: r for r in rows}

    items = []
    known = 0
    review_later = 0
    seen = 0

    for i in range(total):
        r = by_idx.get(i)
        status = r.status if r else None
        seen_count = r.seen_count if r else 0
        if seen_count > 0:
            seen += 1
        if status == "known":
            known += 1
        if status == "review_later":
            review_later += 1

        items.append(
            {
                "card_index": i,
                "status": status,
                "seen_count": seen_count,
                "known_count": (r.known_count if r else 0),
                "review_later_count": (r.review_later_count if r else 0),
                "last_seen_at": (r.last_seen_at.isoformat() if (r and r.last_seen_at) else None),
            }
        )

    return {
        "study_pack_id": study_pack_id,
        "total_cards": total,
        "seen_cards": seen,
        "known_cards": known,
        "review_later_cards": review_later,
        "items": items,
    }


def mark_flashcard(
    db: Session,
    study_pack_id: int,
    card_index: int,
    action: str,
) -> dict[str, Any]:
    """
    action:
      - "known"
      - "review_later"
      - "reset"
      - "seen"  (optional, just bumps seen_count)
    """
    if card_index < 0:
        raise ValueError("card_index must be >= 0")

    cards = _load_flashcards(db, study_pack_id)
    if not cards:
        raise ValueError("No flashcards found for this pack. Generate materials first.")
    if card_index >= len(cards):
        raise ValueError(f"card_index out of range (0..{len(cards)-1})")

    row = (
        db.query(FlashcardProgress)
        .filter(
            FlashcardProgress.study_pack_id == study_pack_id,
            FlashcardProgress.card_index == card_index,
        )
        .first()
    )
    if not row:
        row = FlashcardProgress(study_pack_id=study_pack_id, card_index=card_index)
        db.add(row)

    row.seen_count = int(row.seen_count or 0) + 1
    row.last_seen_at = _now()

    if action == "known":
        row.status = "known"
        row.known_count = int(row.known_count or 0) + 1
    elif action == "review_later":
        row.status = "review_later"
        row.review_later_count = int(row.review_later_count or 0) + 1
    elif action == "reset":
        row.status = None
    elif action == "seen":
        pass
    else:
        raise ValueError("Invalid action. Use one of: known, review_later, reset, seen")

    db.commit()
    db.refresh(row)

    # return refreshed summary (cheap and keeps UI simple)
    return get_flashcards_progress(db, study_pack_id)