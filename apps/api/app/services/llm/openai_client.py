from __future__ import annotations

import os
import re
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v and v.strip() else default


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def _clip(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " …"


# ---------- Structured output schema (Pydantic) ----------

class SummaryOut(BaseModel):
    text: str = Field(..., description="A concise, high-signal summary of the transcript.")


class KeyTakeawaysOut(BaseModel):
    items: List[str] = Field(..., description="5–10 key takeaways as short bullet-style sentences.")


class ChapterOut(BaseModel):
    title: str
    summary: str
    sentences: List[str]


class ChaptersOut(BaseModel):
    items: List[ChapterOut]


class FlashcardOut(BaseModel):
    q: str
    a: str


class FlashcardsOut(BaseModel):
    items: List[FlashcardOut]


class QuizItemOut(BaseModel):
    question: str
    options: List[str]
    answer_index: int


class QuizOut(BaseModel):
    items: List[QuizItemOut]


class StudyMaterialsOut(BaseModel):
    summary: SummaryOut
    key_takeaways: KeyTakeawaysOut
    chapters: ChaptersOut
    flashcards: FlashcardsOut
    quiz: QuizOut


# ---------- Public function used by study_materials.py ----------

def generate_study_materials_openai(transcript_text: str) -> dict:
    """
    Generate study materials using OpenAI, returning a dict shaped like:
    {
      "summary": {"text": ...},
      "key_takeaways": {"items": [...]},
      "chapters": {"items": [{"title":..., "summary":..., "sentences":[...]}]},
      "flashcards": {"items": [{"q":..., "a":...}]},
      "quiz": {"items": [{"question":..., "options":[...], "answer_index":0}]}
    }
    """
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = _env("OPENAI_MODEL", "gpt-4o-mini")

    # Keep prompts bounded for V0.
    # If you want full-length later: chunk transcript and merge outputs.
    cleaned = _clean_text(transcript_text)
    clipped = _clip(cleaned, max_chars=int(_env("OPENAI_MAX_TRANSCRIPT_CHARS", "20000") or "20000"))

    system = (
        "You are an expert learning designer. You will receive a transcript. "
        "Generate study materials that help a learner revise quickly.\n\n"
        "Requirements:\n"
        "- Output must match the provided schema exactly.\n"
        "- Summary: 5–10 lines, plain English.\n"
        "- Key takeaways: 5–10 items, each 1 sentence.\n"
        "- Chapters: 3–8 chapters depending on transcript length; each chapter has a short summary and 3–8 sentences.\n"
        "- Flashcards: 8–15 items, Q/A based on the content.\n"
        "- Quiz: 5–8 MCQs; each has 4 options; answer_index must be correct.\n"
        "- Do not include filler or unrelated lyrics/noise. If transcript is noisy, focus on meaningful parts."
    )

    user = (
        "Transcript:\n"
        f"{clipped}\n\n"
        "Return the study materials."
    )

    client = OpenAI(api_key=api_key)

    # Use Structured Outputs (parse) so schema is enforced.
    # This matches OpenAI docs for responses.parse + Pydantic schemas.  [oai_citation:1‡OpenAI](https://platform.openai.com/docs/guides/structured-outputs)
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        text_format=StudyMaterialsOut,
    )

    parsed: StudyMaterialsOut = response.output_parsed  # type: ignore[attr-defined]

    # Pydantic v2 uses model_dump(); v1 uses dict().
    if hasattr(parsed, "model_dump"):
        return parsed.model_dump()
    return parsed.dict()