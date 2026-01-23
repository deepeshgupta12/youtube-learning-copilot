from __future__ import annotations

import json
import os
from typing import Any

from app.services.llm.prompts import STUDY_MATERIALS_SYSTEM, STUDY_MATERIALS_USER_TEMPLATE


def generate_study_materials_openai(transcript_text: str) -> dict[str, Any]:
    """
    OpenAI-backed generation. Returns the same payload schema as heuristic.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # using the modern OpenAI python SDK style (Responses API).
    # If your repo uses older SDK, tell me and I'll adjust.
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    user_prompt = STUDY_MATERIALS_USER_TEMPLATE.format(transcript=transcript_text)

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": STUDY_MATERIALS_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        # Force JSON output if supported by model; still parse defensively
        response_format={"type": "json_object"},
    )

    text = resp.output_text
    try:
        payload = json.loads(text)
    except Exception as e:
        raise ValueError(f"OpenAI returned non-JSON: {e}. First 200 chars: {text[:200]!r}")

    return payload