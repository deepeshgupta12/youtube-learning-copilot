from __future__ import annotations

import json
import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack


# -----------------------------
# Public helpers
# -----------------------------

def material_text(kind: str, payload: Any) -> str | None:
    """
    Create a text fallback for UI/search even if payload is JSON.
    Keep it simple and deterministic for V0.
    """
    if payload is None:
        return None

    # If someone accidentally passes a JSON string, try to parse it.
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            # If it's just raw text, for summary we can return it
            if kind == "summary":
                return payload.strip() or None
            return payload.strip() or None

    if not isinstance(payload, dict):
        # Unexpected shape, best-effort stringify.
        s = str(payload).strip()
        return s or None

    if kind == "summary":
        # payload: {"text": "..."}
        text = payload.get("text")
        return str(text).strip() if text else None

    if kind == "key_takeaways":
        # payload: {"items": ["...", "..."]}
        items = payload.get("items") or []
        if not items:
            return None
        return "\n".join([f"- {str(x).strip()}" for x in items if str(x).strip()]) or None

    if kind == "chapters":
        # payload: {"items":[{"title":..., "summary":...}, ...]}
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for ch in items:
            if not isinstance(ch, dict):
                continue
            title = ch.get("title")
            summ = ch.get("summary")
            if title:
                lines.append(str(title).strip())
            if summ:
                lines.append(str(summ).strip())
            lines.append("")  # spacer
        text = "\n".join(lines).strip()
        return text or None

    if kind == "flashcards":
        # payload: {"items":[{"q":..., "a":...}, ...]}
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for i, fc in enumerate(items, start=1):
            if not isinstance(fc, dict):
                continue
            q = fc.get("q")
            a = fc.get("a")
            if q:
                lines.append(f"Q{i}. {str(q).strip()}")
            if a:
                lines.append(f"A{i}. {str(a).strip()}")
            lines.append("")
        text = "\n".join(lines).strip()
        return text or None

    if kind == "quiz":
        # payload: {"items":[{"question":..., "options":[...], "answer_index":...}, ...]}
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for i, q in enumerate(items, start=1):
            if not isinstance(q, dict):
                continue
            question = q.get("question")
            options = q.get("options") or []
            answer_index = q.get("answer_index")
            if question:
                lines.append(f"Q{i}. {str(question).strip()}")
            for j, opt in enumerate(options, start=1):
                lines.append(f"  {j}) {str(opt).strip()}")
            if isinstance(answer_index, int) and 0 <= answer_index < len(options):
                lines.append(f"Answer: {answer_index + 1}")
            lines.append("")
        text = "\n".join(lines).strip()
        return text or None

    return None


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _simple_sentence_split(text: str) -> list[str]:
    text = _clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


# -----------------------------
# Payload generation (V0)
# -----------------------------

def generate_materials_payload_heuristic(transcript_text: str) -> dict[str, Any]:
    """
    Deterministic V0 generator (no LLM).
    """
    text = _clean_text(transcript_text)
    sents = _simple_sentence_split(text)

    summary = " ".join(sents[:3]) if sents else (text[:400] if text else "")
    if not summary and text:
        summary = text[:400]

    key_takeaways: list[str] = []
    if sents:
        key_takeaways = sents[:5]
    elif text:
        key_takeaways = [text[:120]]

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

    flashcards = []
    for i, t in enumerate(key_takeaways[:10]):
        flashcards.append(
            {
                "q": f"What is one key point from the transcript? (#{i+1})",
                "a": t,
            }
        )

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


def generate_materials_payload(transcript_text: str) -> dict[str, Any]:
    """
    Official entrypoint used everywhere.
    For now (V0), this is still heuristic-only.
    Later you’ll switch this to OpenAI behind a feature flag.
    """
    return generate_materials_payload_heuristic(transcript_text)


# -----------------------------
# DB persistence
# -----------------------------

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

    for kind in ["summary", "key_takeaways", "chapters", "flashcards", "quiz"]:
        obj = payload.get(kind) or {}
        txt = material_text(kind, obj)
        upsert_material(
            db=db,
            study_pack_id=study_pack_id,
            kind=kind,
            status="generated",
            content_json_obj=obj,
            content_text=txt,
            error=None,
        )
# Backward-compatible alias for callers / debug snippets
generate_materials_payload = generate_materials_payload_heuristic  # noqa: F811
        