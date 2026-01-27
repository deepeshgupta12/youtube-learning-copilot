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
    """Create a text fallback for UI/search even if payload is JSON."""
    if not payload:
        return None

    if kind == "summary":
        return payload.get("text")

    if kind == "key_takeaways":
        items = payload.get("items") or []
        items = [str(x).strip() for x in items if str(x).strip()]
        return "\n".join([f"- {x}" for x in items]) if items else None

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


# ----------------------------
# Cleaning helpers
# ----------------------------

_STAGE_DIR_RE = re.compile(
    r"""\[
        (?:\s*music\s*|\s*laughter\s*|\s*applause\s*|\s*inaudible\s*|\s*silence\s*|[^\]]{1,40})
    \]""",
    re.IGNORECASE | re.VERBOSE,
)


def _dedupe_consecutive_ngrams(words: list[str], n: int) -> list[str]:
    """Collapse immediate repetitions like: A B C A B C ... by skipping repeated n-grams."""
    if n <= 1 or len(words) < n * 2:
        return words

    out: list[str] = []
    i = 0
    while i < len(words):
        if len(out) >= n and i + n <= len(words) and out[-n:] == words[i : i + n]:
            i += n
            continue
        out.append(words[i])
        i += 1
    return out


def _clean_text(text: str) -> str:
    """Normalize transcript text for downstream material generation."""
    s = (text or "").strip()
    if not s:
        return ""

    s = _STAGE_DIR_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()

    words = s.split()
    for n in (12, 10, 8, 6):
        words = _dedupe_consecutive_ngrams(words, n)
    s = " ".join(words)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def _chunk_words(text: str, chunk_words: int = 28) -> list[str]:
    words = [w for w in (text or "").split() if w]
    if not words:
        return []
    return [" ".join(words[i : i + chunk_words]).strip() for i in range(0, len(words), chunk_words)]


def _simple_sentence_split(text: str) -> list[str]:
    """Make a 'sentence-like' list from transcript."""
    text = _clean_text(text)
    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) < 6:
        parts = _chunk_words(text, chunk_words=28)

    parts = [p for p in parts if len(p.split()) >= 6]
    return parts


def _pick_evenly(items: list[str], k: int) -> list[str]:
    if not items or k <= 0:
        return []
    if len(items) <= k:
        return items
    idxs = [round(i * (len(items) - 1) / (k - 1)) for i in range(k)]
    out: list[str] = []
    seen = set()
    for ix in idxs:
        s = items[int(ix)]
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:k]


# ----------------------------
# Heuristic V0 generator
# ----------------------------

def generate_materials_payload_heuristic(transcript_text: str) -> dict[str, Any]:
    """Deterministic generator that produces distinct materials even for no-punct transcripts."""
    text = _clean_text(transcript_text)
    sents = _simple_sentence_split(text)

    if sents:
        picks = _pick_evenly(sents, k=3)
        summary = " ".join(picks).strip()
    else:
        summary = (text[:500] if text else "").strip()

    takeaways = _pick_evenly(sents, k=6) if sents else []
    takeaways = [t.strip() for t in takeaways if t.strip()]

    chapters: list[dict[str, Any]] = []
    if sents:
        target_chapters = 6 if len(sents) >= 24 else 4
        per = max(4, (len(sents) + target_chapters - 1) // target_chapters)
        for i in range(0, len(sents), per):
            chunk = sents[i : i + per]
            if not chunk:
                continue
            chapters.append(
                {
                    "title": f"Chapter {len(chapters) + 1}",
                    "summary": " ".join(chunk[:2]).strip(),
                    "sentences": chunk,
                }
            )

    flashcards: list[dict[str, str]] = []
    for i, t in enumerate(takeaways[:10], start=1):
        ans = t.strip()
        if len(ans) > 220:
            ans = " ".join(ans.split()[:40]).strip() + "…"
        flashcards.append({"q": f"Key idea #{i}", "a": ans})

    quiz: list[dict[str, Any]] = []
    for i, t in enumerate(takeaways[:5], start=1):
        correct = t.strip()
        if len(correct) > 180:
            correct = " ".join(correct.split()[:30]).strip() + "…"
        quiz.append(
            {
                "question": f"Which statement matches the transcript? (Q{i})",
                "options": [
                    correct,
                    "The transcript does not mention this",
                    "This contradicts the transcript",
                    "This is an unrelated detail",
                ],
                "answer_index": 0,
            }
        )

    return {
        "summary": {"text": summary},
        "key_takeaways": {"items": takeaways},
        "chapters": {"items": chapters},
        "flashcards": {"items": flashcards},
        "quiz": {"items": quiz},
    }


# ----------------------------
# Validation
# ----------------------------

def _overlap_ratio(a: str, b: str) -> float:
    a = _clean_text(a)
    b = _clean_text(b)
    if not a or not b:
        return 0.0
    if a in b:
        return 1.0
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(1, len(a_tokens))


def validate_payload(
    transcript_text: str,
    payload: dict[str, Any],
    *,
    provider: str = "heuristic",
) -> dict[str, str]:
    """Returns {kind: error_code}. Empty dict = pass."""
    errors: dict[str, str] = {}

    transcript = _clean_text(transcript_text)
    tlen = len(transcript)

    summary_text = (payload.get("summary") or {}).get("text") or ""
    summary_text = _clean_text(summary_text)

    # Only enforce synthesized constraints for OpenAI output (heuristic is extractive by design)
    if provider == "openai" and tlen > 600:
        if len(summary_text) > 1200:
            errors["summary"] = "summary_too_long"
        elif _overlap_ratio(summary_text, transcript) > 0.70:
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


def _with_meta(obj: dict[str, Any] | None, meta: dict[str, Any]) -> dict[str, Any]:
    base = obj or {}
    if not isinstance(base, dict):
        return {"_meta": meta, "data": base}
    out = dict(base)
    out["_meta"] = meta
    return out


# ----------------------------
# Main entrypoint used by Celery task
# ----------------------------

def generate_and_store_all(db: Session, study_pack_id: int) -> None:
    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        raise ValueError(f"StudyPack not found: {study_pack_id}")

    if not sp.transcript_text:
        raise ValueError("StudyPack transcript_text is empty; ingest first.")

    requested_provider = os.getenv("STUDY_MATERIALS_PROVIDER", "heuristic").lower()
    transcript_clean = _clean_text(sp.transcript_text)

    payload: dict[str, Any]
    provider_used = "heuristic"
    openai_error: str | None = None

    if requested_provider == "openai":
        try:
            from app.services.llm.openai_client import generate_study_materials_openai
            payload = generate_study_materials_openai(transcript_clean)
            provider_used = "openai"
        except Exception as e:
            openai_error = str(e)
            payload = generate_materials_payload_heuristic(transcript_clean)
            provider_used = "heuristic"
    else:
        payload = generate_materials_payload_heuristic(transcript_clean)
        provider_used = "heuristic"

    meta = {
        "requested_provider": requested_provider,
        "provider": provider_used,
        "openai_model": os.getenv("OPENAI_MODEL", None),
        "openai_error": openai_error,
        "transcript_len": len(sp.transcript_text or ""),
        "transcript_clean_len": len(transcript_clean),
    }

    errs = validate_payload(transcript_clean, payload, provider=provider_used)

    # If OpenAI failed, surface the root error in every row (while storing heuristic fallback)
    if openai_error:
        for k in ["summary", "key_takeaways", "chapters", "flashcards", "quiz"]:
            errs.setdefault(k, f"OpenAI failed; stored heuristic fallback. Root error: {openai_error}")

    kinds = ["summary", "key_takeaways", "chapters", "flashcards", "quiz"]
    for kind in kinds:
        kind_obj = payload.get(kind) or {}
        kind_obj = _with_meta(kind_obj if isinstance(kind_obj, dict) else {"data": kind_obj}, meta)

        upsert_material(
            db,
            study_pack_id,
            kind,
            status="generated",
            content_json_obj=kind_obj,
            content_text=material_text(kind, kind_obj),
            error=errs.get(kind),
        )