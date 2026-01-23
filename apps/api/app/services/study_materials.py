from __future__ import annotations

import json
import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack


# ----------------------------
# Text helpers
# ----------------------------

def material_text(kind: str, payload: dict) -> str | None:
    """
    Create a text fallback for UI/search even if payload is JSON.
    Keep it simple and deterministic for V0.
    """
    if not payload:
        return None

    if kind == "summary":
        return payload.get("text")

    if kind == "key_takeaways":
        items = payload.get("items") or []
        if not items:
            return None
        return "\n".join([f"- {x}" for x in items if x])

    if kind == "chapters":
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for ch in items:
            title = ch.get("title")
            summ = ch.get("summary")
            if title:
                lines.append(str(title))
            if summ:
                lines.append(str(summ))
            lines.append("")
        text = "\n".join(lines).strip()
        return text or None

    if kind == "flashcards":
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for i, fc in enumerate(items, start=1):
            q = fc.get("q")
            a = fc.get("a")
            if q:
                lines.append(f"Q{i}. {q}")
            if a:
                lines.append(f"A{i}. {a}")
            lines.append("")
        text = "\n".join(lines).strip()
        return text or None

    if kind == "quiz":
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for i, q in enumerate(items, start=1):
            question = q.get("question")
            options = q.get("options") or []
            answer_index = q.get("answer_index")
            if question:
                lines.append(f"Q{i}. {question}")
            for j, opt in enumerate(options, start=1):
                lines.append(f"  {j}) {opt}")
            if isinstance(answer_index, int) and 0 <= answer_index < len(options):
                lines.append(f"Answer: {answer_index + 1}")
            lines.append("")
        text = "\n".join(lines).strip()
        return text or None

    return None


def _clean_text(text: str) -> str:
    # keep musical symbols, but normalize whitespace
    return re.sub(r"\s+", " ", text or "").strip()


def _simple_sentence_split(text: str) -> list[str]:
    """
    Slightly improved splitter:
    - First normalizes whitespace
    - If punctuation-based split yields only 1 chunk, try splitting on '♪' or line-like separators.
    """
    text = _clean_text(text)
    if not text:
        return []

    # punctuation-based
    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]

    # if transcript has no punctuation (lyrics), fallback split
    if len(parts) <= 1:
        # split on musical notes / long dash / pipes as "pseudo sentences"
        alt = re.split(r"(?:\u266a+|\[.*?\]|\s-\s|\s\|\s)", text)
        alt = [a.strip() for a in alt if a.strip()]
        # if still too big, chunk by fixed length
        if len(alt) <= 1 and len(text) > 300:
            step = 180
            alt = [text[i:i+step].strip() for i in range(0, len(text), step) if text[i:i+step].strip()]
        return alt

    return parts


# ----------------------------
# Heuristic V0 generator
# ----------------------------

def generate_materials_payload_heuristic(transcript_text: str) -> dict[str, Any]:
    """
    Deterministic V0 generator (improved splitter).
    """
    text = _clean_text(transcript_text)
    sents = _simple_sentence_split(text)

    summary = " ".join(sents[:3]) if sents else (text[:400] if text else "")
    key_takeaways: list[str] = []
    if sents:
        key_takeaways = sents[:5]
    elif text:
        key_takeaways = [text[:120]]

    chapters: list[dict[str, Any]] = []
    chunk_size = 6
    for i in range(0, len(sents), chunk_size):
        chunk = sents[i: i + chunk_size]
        if not chunk:
            continue
        chapters.append(
            {
                "title": f"Chapter {len(chapters) + 1}",
                "summary": " ".join(chunk[:2]),
                "sentences": chunk,
            }
        )

    flashcards: list[dict[str, str]] = []
    for i, t in enumerate(key_takeaways[:10]):
        flashcards.append({"q": f"What is one key point from the transcript? (#{i+1})", "a": t})

    quiz: list[dict[str, Any]] = []
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


# ----------------------------
# Guardrails
# ----------------------------

def _overlap_ratio(a: str, b: str) -> float:
    """
    Cheap containment heuristic: fraction of summary contained in transcript.
    """
    a = _clean_text(a)
    b = _clean_text(b)
    if not a or not b:
        return 0.0
    if a in b:
        return 1.0
    # token overlap
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(1, len(a_tokens))


def validate_payload(transcript_text: str, payload: dict[str, Any]) -> dict[str, str]:
    """
    Returns {kind: error_code} for failures. Empty dict = pass.
    """
    errors: dict[str, str] = {}

    transcript = _clean_text(transcript_text)
    tlen = len(transcript)

    summary_text = (payload.get("summary") or {}).get("text") or ""
    summary_text = _clean_text(summary_text)

    # If transcript is long but summary is also long or highly overlapping => not synthesized
    if tlen > 600:
        if len(summary_text) > 1200:
            errors["summary"] = "summary_too_long"
        elif _overlap_ratio(summary_text, transcript) > 0.75:
            errors["summary"] = "summary_not_synthesized"

    takeaways = ((payload.get("key_takeaways") or {}).get("items") or [])
    takeaways = [str(x).strip() for x in takeaways if str(x).strip()]
    if tlen > 400 and len(takeaways) < 5:
        errors["key_takeaways"] = "takeaways_too_few"
    if takeaways and any(len(x) > 260 for x in takeaways):
        errors["key_takeaways"] = "takeaways_too_long"

    chapters = ((payload.get("chapters") or {}).get("items") or [])
    if tlen > 800 and len(chapters) < 2:
        errors["chapters"] = "chapters_too_few"

    flashcards = ((payload.get("flashcards") or {}).get("items") or [])
    if tlen > 400 and len(flashcards) < 8:
        errors["flashcards"] = "flashcards_too_few"

    quiz = ((payload.get("quiz") or {}).get("items") or [])
    if tlen > 400 and len(quiz) < 5:
        errors["quiz"] = "quiz_too_few"

    return errors


# ----------------------------
# DB upsert
# ----------------------------

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


# ----------------------------
# Main entrypoint used by Celery task
# ----------------------------

def generate_and_store_all(db: Session, study_pack_id: int) -> None:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise ValueError(f"StudyPack not found: {study_pack_id}")

    if not sp.transcript_text:
        raise ValueError("StudyPack transcript_text is empty; ingest first.")

    provider = os.getenv("STUDY_MATERIALS_PROVIDER", "heuristic").lower()

    if provider == "openai":
        from app.services.llm.openai_client import generate_study_materials_openai
        payload = generate_study_materials_openai(sp.transcript_text)
    else:
        payload = generate_materials_payload_heuristic(sp.transcript_text)

    # guardrails
    errs = validate_payload(sp.transcript_text, payload)

    kinds = ["summary", "key_takeaways", "chapters", "flashcards", "quiz"]
    for kind in kinds:
        if kind in errs:
            upsert_material(
                db,
                study_pack_id,
                kind,
                status="failed",
                content_json_obj=payload.get(kind),
                content_text=material_text(kind, payload.get(kind) or {}),
                error=errs[kind],
            )
        else:
            upsert_material(
                db,
                study_pack_id,
                kind,
                status="generated",
                content_json_obj=payload.get(kind),
                content_text=material_text(kind, payload.get(kind) or {}),
                error=None,
            )