from __future__ import annotations

import json
import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack


def _is_test_env() -> bool:
    return os.getenv("ENV") == "test"


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def _simple_sentence_split(text: str) -> list[str]:
    # extremely simple splitter (good enough for deterministic V0)
    text = _clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def generate_materials_payload(transcript_text: str) -> dict[str, Any]:
    """
    Deterministic V0 generator.
    - In real (non-test) env, we still keep it deterministic for now to avoid external dependency.
      Later we can add an LLM provider behind a flag.
    """
    text = _clean_text(transcript_text)
    sents = _simple_sentence_split(text)

    summary = " ".join(sents[:3]) if sents else (text[:400] if text else "")
    key_takeaways = []
    if sents:
        key_takeaways = sents[:5]
    elif text:
        key_takeaways = [text[:120]]

    # Chapters: chunk every ~6 sentences
    chapters = []
    chunk_size = 6
    for i in range(0, len(sents), chunk_size):
        chunk = sents[i : i + chunk_size]
        if not chunk:
            continue
        chapters.append(
            {
                "title": f"Chapter {len(chapters) + 1}",
                "summary": " ".join(chunk[:2]),
                "sentences": chunk,
            }
        )

    # Flashcards: naive Q/A based on takeaways
    flashcards = []
    for i, t in enumerate(key_takeaways[:10]):
        flashcards.append(
            {
                "q": f"What is one key point from the transcript? (#{i+1})",
                "a": t,
            }
        )

    # Quiz: naive MCQ
    quiz = []
    for i, t in enumerate(key_takeaways[:5]):
        quiz.append(
            {
                "question": f"Which of the following best matches a point made in the transcript? (#{i+1})",
                "options": [t, "Not mentioned", "Opposite of transcript", "Unrelated detail"],
                "answer_index": 0,
            }
        )

    return {
        "summary": {"text": summary},
        "key_takeaways": {"items": key_takeaways},
        "chapters": {"items": chapters},
        "flashcards": {"items": flashcards},
        "quiz": {"items": quiz},
    }


def upsert_material(
    db: Session,
    study_pack_id: int,
    kind: str,
    status: str,
    content_json_obj: dict[str, Any] | None = None,
    content_text: str | None = None,
    error: str | None = None,
) -> StudyMaterial:
    m = (
        db.query(StudyMaterial)
        .filter(StudyMaterial.study_pack_id == study_pack_id, StudyMaterial.kind == kind)
        .first()
    )
    if not m:
        m = StudyMaterial(study_pack_id=study_pack_id, kind=kind)
        db.add(m)

    m.status = status
    m.content_json = json.dumps(content_json_obj) if content_json_obj is not None else None
    m.content_text = content_text
    m.error = error
    db.commit()
    db.refresh(m)
    return m


def generate_and_store_all(db: Session, study_pack_id: int) -> None:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise ValueError(f"StudyPack not found: {study_pack_id}")

    if not sp.transcript_text:
        raise ValueError("StudyPack transcript_text is empty; ingest first.")

    payload = generate_materials_payload(sp.transcript_text)

    # Store each kind separately
    upsert_material(db, study_pack_id, "summary", "generated", payload["summary"], payload["summary"]["text"])
    upsert_material(db, study_pack_id, "key_takeaways", "generated", payload["key_takeaways"], None)
    upsert_material(db, study_pack_id, "chapters", "generated", payload["chapters"], None)
    upsert_material(db, study_pack_id, "flashcards", "generated", payload["flashcards"], None)
    upsert_material(db, study_pack_id, "quiz", "generated", payload["quiz"], None)