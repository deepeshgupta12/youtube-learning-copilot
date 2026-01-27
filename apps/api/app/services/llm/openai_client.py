from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from app.services.llm.prompts import STUDY_MATERIALS_SYSTEM, STUDY_MATERIALS_USER_TEMPLATE


_STAGE_DIR_RE = re.compile(
    r"""\[
        (?:\s*music\s*|\s*laughter\s*|\s*applause\s*|\s*inaudible\s*|\s*silence\s*|[^\]]{1,40})
    \]""",
    re.IGNORECASE | re.VERBOSE,
)


def _dedupe_consecutive_ngrams(words: list[str], n: int) -> list[str]:
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
    s = (text or "").strip()
    if not s:
        return ""
    s = _STAGE_DIR_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()

    words = s.split()
    # stronger than heuristic path because caption noise is brutal
    for n in (14, 12, 10, 8, 6):
        words = _dedupe_consecutive_ngrams(words, n)
    s = " ".join(words)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _compress_for_llm(text: str, max_words: int = 2200) -> str:
    """
    Keep coverage across the transcript: take head + middle + tail.
    Prevents huge dumps that encourage the model to copy.
    """
    words = [w for w in (text or "").split() if w]
    if not words:
        return ""

    if len(words) <= max_words:
        return " ".join(words)

    third = max_words // 3
    head = words[:third]
    tail = words[-third:]
    mid_start = max(0, (len(words) // 2) - (third // 2))
    mid = words[mid_start : mid_start + third]

    return (
        "HEAD:\n" + " ".join(head) +
        "\n\nMIDDLE:\n" + " ".join(mid) +
        "\n\nTAIL:\n" + " ".join(tail)
    )


def _must_have_keys(payload: dict[str, Any]) -> None:
    required = {"summary", "key_takeaways", "chapters", "flashcards", "quiz"}
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"OpenAI payload missing keys: {missing}")


def _looks_like_transcript_dump(transcript: str, candidate: str) -> bool:
    """
    Detect if candidate is basically copied transcript.
    Heuristic: any 13-word window in candidate appears in transcript.
    """
    t = (transcript or "").lower()
    c = (candidate or "").lower()
    if len(c.split()) < 40:
        return False

    c_words = c.split()
    if len(c_words) < 13:
        return False

    for i in range(0, min(len(c_words) - 13, 120)):  # cap checks
        window = " ".join(c_words[i : i + 13])
        if window and window in t:
            return True
    return False


def _payload_quality_check(transcript_clean: str, payload: dict[str, Any]) -> list[str]:
    """
    Returns list of quality issues (empty => good).
    """
    issues: list[str] = []
    _must_have_keys(payload)

    summary = ((payload.get("summary") or {}).get("text") or "").strip()
    if not summary or len(summary.split()) < 60:
        issues.append("summary too short or empty")
    if _looks_like_transcript_dump(transcript_clean, summary):
        issues.append("summary looks like transcript dump")

    takeaways = ((payload.get("key_takeaways") or {}).get("items") or [])
    if not isinstance(takeaways, list) or len(takeaways) < 5:
        issues.append("key_takeaways missing or too few")
    else:
        # if any takeaway is huge, it's probably copy
        for t in takeaways[:10]:
            if isinstance(t, str) and len(t.split()) > 22:
                issues.append("takeaway too long (likely copied)")
                break

    return issues


def _call_openai_json(model: str, system: str, user: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing")

    client = OpenAI(api_key=api_key)

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.4")),
        max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1600")),
    )

    text = resp.output_text or ""
    try:
        data = json.loads(text)
    except Exception as e:
        raise ValueError(f"OpenAI returned non-JSON: {e}. First 200 chars: {text[:200]!r}")
    if not isinstance(data, dict):
        raise ValueError("OpenAI JSON root must be an object")
    return data


def generate_study_materials_openai(transcript_text: str) -> dict[str, Any]:
    """
    OpenAI-backed generation. Returns payload schema:
    summary, key_takeaways, chapters, flashcards, quiz
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    clean = _clean_text(transcript_text)
    compressed = _compress_for_llm(clean, max_words=int(os.getenv("OPENAI_TRANSCRIPT_MAX_WORDS", "2200")))

    user_prompt = STUDY_MATERIALS_USER_TEMPLATE.format(transcript=compressed)

    payload = _call_openai_json(model, STUDY_MATERIALS_SYSTEM, user_prompt)

    issues = _payload_quality_check(clean, payload)
    if not issues:
        return payload

    # One repair attempt (very effective when the model starts copying)
    repair_user = f"""The JSON you returned has quality issues:
- {chr(10).join(issues)}

Fix the JSON while keeping the same schema.
Remember: never copy >12 consecutive words from the transcript; paraphrase and abstract.

Transcript (cleaned + compressed):
{compressed}

Return corrected JSON only."""
    repaired = _call_openai_json(model, STUDY_MATERIALS_SYSTEM, repair_user)

    # Final validation (if still bad, raise so job fails loudly instead of storing junk)
    issues2 = _payload_quality_check(clean, repaired)
    if issues2:
        raise ValueError(f"OpenAI output failed quality gate: {issues2}")

    return repaired