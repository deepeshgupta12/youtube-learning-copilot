from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Tuple

from app.services.llm.prompts import STUDY_MATERIALS_SYSTEM, STUDY_MATERIALS_USER_TEMPLATE


# ----------------------------
# Transcript compression helpers
# ----------------------------

_STAGE_DIR_RE = re.compile(
    r"""\[
        (?:\s*music\s*|\s*laughter\s*|\s*applause\s*|\s*inaudible\s*|\s*silence\s*|[^\]]{1,40})
    \]""",
    re.IGNORECASE | re.VERBOSE,
)


def _clean_text(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = _STAGE_DIR_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _chunk_words(text: str, chunk_words: int = 28) -> list[str]:
    words = [w for w in (text or "").split() if w]
    if not words:
        return []
    return [" ".join(words[i : i + chunk_words]).strip() for i in range(0, len(words), chunk_words)]


def _simple_sentence_split(text: str) -> list[str]:
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


def _compress_transcript(transcript_text: str, max_chars: int = 9000) -> str:
    """
    Compress transcript by selecting evenly-spaced sentence-like lines.
    This dramatically reduces timeouts while still covering the full video.
    """
    t = _clean_text(transcript_text)
    if not t:
        return ""
    if len(t) <= max_chars:
        return t

    sents = _simple_sentence_split(t)
    if not sents:
        return t[:max_chars]

    # Pick enough lines to reach ~max_chars
    # (start with 50; adjust down if still too large)
    k = 60 if len(sents) > 200 else 45
    picks = _pick_evenly(sents, k=k)
    out = " ".join(picks).strip()

    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0].strip()
    return out


# ----------------------------
# OpenAI call helpers (SDK compatible)
# ----------------------------

def _build_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing")

    timeout_sec = float(os.getenv("OPENAI_TIMEOUT_SEC", "180"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

    # OpenAI SDK v1+
    from openai import OpenAI  # type: ignore

    return OpenAI(api_key=api_key, timeout=timeout_sec, max_retries=max_retries)


def _extract_json(text: str) -> dict[str, Any]:
    """
    Best-effort JSON extraction if model returns extra text.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty response from OpenAI")

    # Fast path
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to find outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        return json.loads(candidate)

    raise ValueError(f"OpenAI returned non-JSON. First 200 chars: {text[:200]!r}")


def _call_openai_json(client, model: str, transcript_compressed: str) -> Tuple[dict[str, Any], str]:
    """
    Tries Responses API first; falls back to ChatCompletions if needed.
    Returns (payload_dict, raw_text_used_for_parsing).
    """
    user_prompt = STUDY_MATERIALS_USER_TEMPLATE.format(transcript=transcript_compressed)

    # Attempt 1: Responses API (newer pattern)
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": STUDY_MATERIALS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            # Some SDK/model combos accept this; if not, we fall back.
            response_format={"type": "json_object"},
        )
        raw_text = getattr(resp, "output_text", None) or ""
        payload = _extract_json(raw_text)
        return payload, raw_text
    except TypeError:
        # SDK doesn’t support response_format for Responses API
        pass
    except Exception:
        # Any other error -> fall through to chat API attempt
        pass

    # Attempt 2: ChatCompletions API (widely supported)
    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": STUDY_MATERIALS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw_text = (chat.choices[0].message.content or "").strip()
        payload = _extract_json(raw_text)
        return payload, raw_text
    except TypeError:
        # Older SDK may not support response_format here either -> do prompt-only JSON
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": STUDY_MATERIALS_SYSTEM},
                {"role": "user", "content": user_prompt + "\n\nReturn ONLY valid JSON."},
            ],
        )
        raw_text = (chat.choices[0].message.content or "").strip()
        payload = _extract_json(raw_text)
        return payload, raw_text


# ----------------------------
# Public API
# ----------------------------

def generate_study_materials_openai(transcript_text: str) -> dict[str, Any]:
    """
    Returns payload:
    {
      "summary": {...},
      "key_takeaways": {...},
      "chapters": {...},
      "flashcards": {...},
      "quiz": {...}
    }
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    transcript_compressed = _compress_transcript(
        transcript_text,
        max_chars=int(os.getenv("OPENAI_TRANSCRIPT_MAX_CHARS", "9000")),
    )

    client = _build_openai_client()

    # Extra backoff loop on timeouts / transient failures
    # (OpenAI SDK already retries, but this helps in Celery/network hiccups)
    attempts = int(os.getenv("OPENAI_ATTEMPTS", "2"))
    last_err: Exception | None = None

    for i in range(attempts):
        try:
            payload, _raw = _call_openai_json(client, model=model, transcript_compressed=transcript_compressed)
            return payload
        except Exception as e:
            last_err = e
            # backoff
            if i < attempts - 1:
                time.sleep(1.5 * (2 ** i))
                continue

    raise RuntimeError(f"OpenAI generation failed after {attempts} attempts: {last_err}")