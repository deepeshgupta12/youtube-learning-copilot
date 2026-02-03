from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.quiz_progress import QuizProgress
from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_quiz(db: Session, study_pack_id: int) -> list[dict[str, Any]]:
    """
    Returns quiz items array from StudyMaterial(kind="quiz").

    Expected shape:
      {"items":[{"question":"...", "options":[...], "answer_index": 0}, ...], "_meta": {...}}
    """
    row = (
        db.query(StudyMaterial)
        .filter(StudyMaterial.study_pack_id == study_pack_id, StudyMaterial.kind == "quiz")
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

        q = it.get("question")
        opts = it.get("options")
        ans = it.get("answer_index")

        if not isinstance(q, str) or not q.strip():
            continue
        if not isinstance(opts, list) or not all(isinstance(o, str) for o in opts) or len(opts) < 2:
            continue
        # answer_index is optional for display, but if present must be int
        if ans is not None and not isinstance(ans, int):
            ans = None

        out.append({"question": q, "options": opts, "answer_index": ans})

    return out


def get_quiz_progress(db: Session, study_pack_id: int) -> dict[str, Any]:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise ValueError("Study pack not found")

    questions = _load_quiz(db, study_pack_id)
    total = len(questions)

    rows = (
        db.query(QuizProgress)
        .filter(QuizProgress.study_pack_id == study_pack_id)
        .all()
    )
    by_idx = {r.question_index: r for r in rows}

    items: list[dict[str, Any]] = []
    seen = 0
    correct = 0
    wrong = 0

    for i in range(total):
        r = by_idx.get(i)
        status = r.status if r else None

        seen_count = int(r.seen_count or 0) if r else 0
        if seen_count > 0:
            seen += 1

        if status == "correct":
            correct += 1
        if status == "wrong":
            wrong += 1

        items.append(
            {
                "question_index": i,
                "status": status,
                "seen_count": seen_count,
                "correct_count": int(r.correct_count or 0) if r else 0,
                "wrong_count": int(r.wrong_count or 0) if r else 0,
                "last_seen_at": (r.last_seen_at.isoformat() if (r and r.last_seen_at) else None),
            }
        )

    return {
        "study_pack_id": study_pack_id,
        "total_questions": total,
        "seen_questions": seen,
        "correct_questions": correct,
        "wrong_questions": wrong,
        "items": items,
    }


def mark_quiz_question(
    db: Session,
    study_pack_id: int,
    question_index: int,
    action: str,
) -> dict[str, Any]:
    """
    action:
      - "correct"
      - "wrong"
      - "reset"
      - "seen"
    """
    if question_index < 0:
        raise ValueError("question_index must be >= 0")

    questions = _load_quiz(db, study_pack_id)
    if not questions:
        raise ValueError("No quiz found for this pack. Generate materials first.")
    if question_index >= len(questions):
        raise ValueError(f"question_index out of range (0..{len(questions)-1})")

    row = (
        db.query(QuizProgress)
        .filter(
            QuizProgress.study_pack_id == study_pack_id,
            QuizProgress.question_index == question_index,
        )
        .first()
    )
    if not row:
        row = QuizProgress(study_pack_id=study_pack_id, question_index=question_index)
        db.add(row)

    row.seen_count = int(row.seen_count or 0) + 1
    row.last_seen_at = _now()

    if action == "correct":
        row.status = "correct"
        row.correct_count = int(row.correct_count or 0) + 1
    elif action == "wrong":
        row.status = "wrong"
        row.wrong_count = int(row.wrong_count or 0) + 1
    elif action == "reset":
        row.status = None
    elif action == "seen":
        pass
    else:
        raise ValueError("Invalid action. Use one of: correct, wrong, reset, seen")

    db.commit()
    db.refresh(row)

    return get_quiz_progress(db, study_pack_id)