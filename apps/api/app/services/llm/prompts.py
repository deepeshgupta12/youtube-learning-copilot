from __future__ import annotations

STUDY_MATERIALS_SYSTEM = """You are an expert learning designer.
Given a raw YouTube transcript, produce structured study materials.

Rules:
- Be faithful to transcript; do not invent facts.
- Keep outputs concise, high-signal.
- Do NOT return markdown. Return ONLY valid JSON.
- JSON must match the schema in the user message exactly.
"""

STUDY_MATERIALS_USER_TEMPLATE = """Transcript:
{transcript}

Return JSON with this exact shape:
{{
  "summary": {{ "text": "..." }},
  "key_takeaways": {{ "items": ["...", "...", "...", "...", "..."] }},
  "chapters": {{ "items": [{{"title":"...", "summary":"...", "sentences":["...","..."]}}] }},
  "flashcards": {{ "items": [{{"q":"...", "a":"..."}}] }},
  "quiz": {{ "items": [{{"question":"...", "options":["...","...","...","..."], "answer_index": 0}}] }}
}}

Constraints:
- summary: 80-160 words, not a transcript dump
- key_takeaways: 5-10 items, each <= 20 words
- chapters: 3-7 chapters if transcript is long; each chapter should reflect a distinct part
- flashcards: 10-20 items; questions should test understanding
- quiz: 5-10 questions; options should be plausible; answer_index points to correct option (0-based)
"""