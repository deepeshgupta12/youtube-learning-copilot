from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack


# ----------------------------
# Text helpers
# ----------------------------

def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return str(x)
    except Exception:
        return ""


def _as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _coerce_flashcard_item(item: Any) -> dict[str, str] | None:
    """
    Accepts:
      - {"q": "...", "a": "..."}
      - {"question": "...", "answer": "..."} (alt keys)
      - "Q: ... A: ..." (string)
      - any other scalar -> becomes answer text
    Returns normalized dict {"q": "...", "a": "..."} or None if empty.
    """
    if item is None:
        return None

    if isinstance(item, dict):
        q = _safe_str(item.get("q") or item.get("question") or "").strip()
        a = _safe_str(item.get("a") or item.get("answer") or "").strip()

        # If dict contains only one field, treat it as answer
        if not a and not q:
            # Try common single-field cases
            if "text" in item:
                a = _safe_str(item.get("text")).strip()
            elif "content" in item:
                a = _safe_str(item.get("content")).strip()

        if not q and a:
            # Provide a generic question if missing
            q = "Key idea"

        if q or a:
            return {"q": q or "Key idea", "a": a}
        return None

    if isinstance(item, str):
        s = item.strip()
        if not s:
            return None

        # Try split on "A:" or "Answer:"
        m = re.split(r"\bA(?:nswer)?:\s*", s, maxsplit=1, flags=re.IGNORECASE)
        if len(m) == 2:
            left = m[0]
            right = m[1]
            left = re.sub(r"^\s*Q(?:uestion)?:\s*", "", left.strip(), flags=re.IGNORECASE)
            q = left.strip() or "Key idea"
            a = right.strip()
            return {"q": q, "a": a}

        # If string has " - " separator
        if " - " in s:
            parts = s.split(" - ", 1)
            q = parts[0].strip() or "Key idea"
            a = parts[1].strip()
            return {"q": q, "a": a}

        # Otherwise treat whole string as answer
        return {"q": "Key idea", "a": s}

    # Fallback for non-string scalars
    s = _safe_str(item).strip()
    if not s:
        return None
    return {"q": "Key idea", "a": s}


def _coerce_quiz_item(item: Any) -> dict[str, Any] | None:
    """
    Accepts:
      - {"question": "...", "options": [...], "answer_index": 0}
      - {"q": "...", "choices": [...], "answer": 2} (alt keys)
      - string -> becomes question with generic options
    Returns normalized dict or None.
    """
    if item is None:
        return None

    if isinstance(item, dict):
        question = _safe_str(item.get("question") or item.get("q") or "").strip()
        options = item.get("options") or item.get("choices") or []
        options_list = [ _safe_str(o).strip() for o in _as_list(options) if _safe_str(o).strip() ]

        ans = item.get("answer_index")
        if ans is None:
            ans = item.get("answer")
        try:
            answer_index = int(ans) if ans is not None else None
        except Exception:
            answer_index = None

        if question and not options_list:
            options_list = ["Option A", "Option B", "Option C", "Option D"]

        out: dict[str, Any] = {"question": question, "options": options_list}
        if isinstance(answer_index, int):
            out["answer_index"] = answer_index
        return out if question else None

    if isinstance(item, str):
        s = item.strip()
        if not s:
            return None
        return {
            "question": s,
            "options": ["True", "False", "Not mentioned", "Unclear"],
            "answer_index": 0,
        }

    s = _safe_str(item).strip()
    if not s:
        return None
    return {
        "question": s,
        "options": ["True", "False", "Not mentioned", "Unclear"],
        "answer_index": 0,
    }


def normalize_materials_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Defensive normalization layer for LLM outputs.
    Ensures the expected shapes:
      - summary: {"text": str}
      - key_takeaways: {"items": list[str]}
      - chapters: {"items": list[dict]}
      - flashcards: {"items": list[{"q": str, "a": str}]}
      - quiz: {"items": list[{"question": str, "options": list[str], "answer_index": int?}]}
    """
    if not isinstance(payload, dict):
        return {}

    out: dict[str, Any] = dict(payload)

    # summary
    summary = out.get("summary")
    if isinstance(summary, str):
        out["summary"] = {"text": summary}
    elif isinstance(summary, dict):
        out["summary"] = {"text": _safe_str(summary.get("text")).strip()}

    # key_takeaways
    kt = out.get("key_takeaways")
    if isinstance(kt, dict):
        items = kt.get("items")
        if isinstance(items, str):
            items_list = [x.strip() for x in re.split(r"[\n•\-]+", items) if x.strip()]
        else:
            items_list = [_safe_str(x).strip() for x in _as_list(items)]
            items_list = [x for x in items_list if x]
        out["key_takeaways"] = {"items": items_list}
    elif isinstance(kt, list):
        out["key_takeaways"] = {"items": [_safe_str(x).strip() for x in kt if _safe_str(x).strip()]}
    elif isinstance(kt, str):
        items_list = [x.strip() for x in re.split(r"[\n•\-]+", kt) if x.strip()]
        out["key_takeaways"] = {"items": items_list}

    # chapters
    ch = out.get("chapters")
    if isinstance(ch, dict):
        items = ch.get("items")
        items_list: list[dict[str, Any]] = []
        for x in _as_list(items):
            if isinstance(x, dict):
                items_list.append(x)
            elif isinstance(x, str) and x.strip():
                items_list.append({"title": "Chapter", "summary": x.strip(), "sentences": [x.strip()]})
        out["chapters"] = {"items": items_list}
    elif isinstance(ch, list):
        items_list = []
        for x in ch:
            if isinstance(x, dict):
                items_list.append(x)
            elif isinstance(x, str) and x.strip():
                items_list.append({"title": "Chapter", "summary": x.strip(), "sentences": [x.strip()]})
        out["chapters"] = {"items": items_list}

    # flashcards
    fc = out.get("flashcards")
    if isinstance(fc, dict):
        items = fc.get("items")
        norm_items: list[dict[str, str]] = []
        for x in _as_list(items):
            obj = _coerce_flashcard_item(x)
            if obj and (obj.get("q") or obj.get("a")):
                norm_items.append(obj)
        out["flashcards"] = {"items": norm_items}
    elif isinstance(fc, list):
        norm_items = []
        for x in fc:
            obj = _coerce_flashcard_item(x)
            if obj and (obj.get("q") or obj.get("a")):
                norm_items.append(obj)
        out["flashcards"] = {"items": norm_items}
    elif isinstance(fc, str) and fc.strip():
        # Split into lines as separate flashcards
        norm_items = []
        for line in fc.splitlines():
            obj = _coerce_flashcard_item(line)
            if obj:
                norm_items.append(obj)
        out["flashcards"] = {"items": norm_items}

    # quiz
    qz = out.get("quiz")
    if isinstance(qz, dict):
        items = qz.get("items")
        norm_items: list[dict[str, Any]] = []
        for x in _as_list(items):
            obj = _coerce_quiz_item(x)
            if obj:
                norm_items.append(obj)
        out["quiz"] = {"items": norm_items}
    elif isinstance(qz, list):
        norm_items = []
        for x in qz:
            obj = _coerce_quiz_item(x)
            if obj:
                norm_items.append(obj)
        out["quiz"] = {"items": norm_items}
    elif isinstance(qz, str) and qz.strip():
        norm_items = []
        for line in qz.splitlines():
            obj = _coerce_quiz_item(line)
            if obj:
                norm_items.append(obj)
        out["quiz"] = {"items": norm_items}

    return out


def material_text(kind: str, payload: dict) -> str | None:
    """Create a text fallback for UI/search even if payload is JSON."""
    if not payload or not isinstance(payload, dict):
        return None

    if kind == "summary":
        return _safe_str(payload.get("text")).strip() or None

    if kind == "key_takeaways":
        items = payload.get("items") or []
        items = [str(x).strip() for x in _as_list(items) if str(x).strip()]
        return "\n".join([f"- {x}" for x in items]) if items else None

    if kind == "chapters":
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for ch in _as_list(items):
            if isinstance(ch, dict):
                title = _safe_str(ch.get("title")).strip()
                summ = _safe_str(ch.get("summary")).strip()
                if title:
                    lines.append(title)
                if summ:
                    lines.append(summ)
                lines.append("")
            else:
                s = _safe_str(ch).strip()
                if s:
                    lines.append(s)
                    lines.append("")
        text = "\n".join(lines).strip()
        return text or None

    if kind == "flashcards":
        items = payload.get("items") or []
        if not items:
            return None
        lines: list[str] = []
        for i, fc in enumerate(_as_list(items), start=1):
            obj = _coerce_flashcard_item(fc)
            if not obj:
                continue
            q = _safe_str(obj.get("q")).strip()
            a = _safe_str(obj.get("a")).strip()
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
        for i, q in enumerate(_as_list(items), start=1):
            obj = _coerce_quiz_item(q)
            if not obj:
                continue
            question = _safe_str(obj.get("question")).strip()
            options = obj.get("options") or []
            options = [_safe_str(o).strip() for o in _as_list(options) if _safe_str(o).strip()]
            answer_index = obj.get("answer_index")

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

    # Normalize payload defensively (critical fix for your crash)
    payload = normalize_materials_payload(payload)

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
        if not isinstance(kind_obj, dict):
            kind_obj = {"data": kind_obj}
        kind_obj = _with_meta(kind_obj, meta)

        upsert_material(
            db,
            study_pack_id,
            kind,
            status="generated",
            content_json_obj=kind_obj,
            content_text=material_text(kind, kind_obj),
            error=errs.get(kind),
        )
    return meta