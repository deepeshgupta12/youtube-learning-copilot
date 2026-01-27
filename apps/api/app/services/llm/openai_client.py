from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from app.services.llm.prompts import STUDY_MATERIALS_SYSTEM, STUDY_MATERIALS_USER_TEMPLATE


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Parse JSON from model output.
    1) Try direct json.loads
    2) Try to extract the first {...} block and parse
    """
    if not text:
        raise ValueError("OpenAI returned empty output")

    text = text.strip()

    # direct
    try:
        return json.loads(text)
    except Exception:
        pass

    # try extract a JSON object substring
    m = _JSON_RE.search(text)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except Exception as e:
            raise ValueError(f"Failed to parse extracted JSON: {e}. First 200 chars: {candidate[:200]!r}")

    raise ValueError(f"OpenAI returned non-JSON. First 200 chars: {text[:200]!r}")


def generate_study_materials_openai(transcript_text: str) -> dict[str, Any]:
    """
    OpenAI-backed generation. Returns payload with keys:
      summary, key_takeaways, chapters, flashcards, quiz
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    user_prompt = STUDY_MATERIALS_USER_TEMPLATE.format(transcript=transcript_text)

    # --- Preferred path: Chat Completions with JSON response_format (widely supported) ---
    # If the installed SDK / model doesn't support response_format, we fall back to prompt-only JSON.
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": STUDY_MATERIALS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            # Many SDK versions support this on chat.completions
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        return _extract_json(text)
    except TypeError:
        # response_format not supported in this SDK version for chat.completions
        pass

    # --- Fallback path: No response_format, force JSON via prompt + parse defensively ---
    # Add an extra hard rule to reduce garbage output.
    forced_user = user_prompt + "\n\nIMPORTANT: Return ONLY a single valid JSON object. No prose. No markdown."
    resp2 = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STUDY_MATERIALS_SYSTEM},
            {"role": "user", "content": forced_user},
        ],
        temperature=0.2,
    )
    text2 = (resp2.choices[0].message.content or "").strip()
    return _extract_json(text2)