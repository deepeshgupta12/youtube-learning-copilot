# apps/api/app/services/kb_qa.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.kb_search import kb_search_chunks


@dataclass
class KBCitation:
    chunk_id: int
    idx: int
    start_sec: float
    end_sec: float
    text: str
    score: float


@dataclass
class KBAskResult:
    refused: bool
    answer: str
    model: str
    citations: List[KBCitation]
    retrieval: Dict[str, Any]


def _normalize_question(q: str) -> str:
    return (q or "").strip()


def _clip(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 3].rstrip() + "..."


def _ollama_generate(*, base_url: str, model: str, prompt: str) -> str:
    """
    Minimal Ollama call (no streaming) with safer timeouts & bounded output.

    Env overrides:
      - OLLAMA_TIMEOUT_SEC (default 300)
      - OLLAMA_NUM_PREDICT (default 256)
      - OLLAMA_TEMPERATURE (default 0.2)
    """
    timeout_sec = float(os.getenv("OLLAMA_TIMEOUT_SEC", "300"))
    num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "256"))
    temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))

    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": num_predict,   # hard cap output tokens
            "temperature": temperature,   # keep it stable
        },
    }

    timeout = httpx.Timeout(timeout_sec, connect=10.0)
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()


def ask_grounded(
    *,
    db: Session,
    study_pack_id: int,
    question: str,
    model: Optional[str] = None,
    limit: int = 6,
    hybrid: bool = True,
    min_best_score: float = 0.52,
) -> KBAskResult:
    """
    V2.3 — Grounded Q&A over transcript chunks (pgvector retrieval + Ollama).

    - Retrieves top chunks using kb_search_chunks(query=question)
    - Refuses if evidence is missing / best_score below threshold
    - Answer must cite sources like [1], [2] ...
    """
    q = _normalize_question(question)
    llm_model = model or getattr(settings, "ollama_model", "qwen2.5:7b-instruct")
    base_url = getattr(settings, "ollama_base_url", "http://localhost:11434")

    if not q:
        return KBAskResult(
            refused=True,
            answer="I can’t answer because the question is empty. Please ask a specific question.",
            model=llm_model,
            citations=[],
            retrieval={
                "study_pack_id": study_pack_id,
                "limit": int(limit),
                "hybrid": bool(hybrid),
                "min_best_score": float(min_best_score),
                "best_score": None,
                "reason": "empty_question",
            },
        )

    top_k = max(1, int(limit))
    retrieval_k = min(24, max(top_k * 4, top_k))

    items = kb_search_chunks(
        db=db,
        study_pack_id=study_pack_id,
        query=q,  # alias supported by kb_search_chunks
        limit=retrieval_k,
        model="sentence-transformers/all-MiniLM-L6-v2",
        hybrid=bool(hybrid),
    )

    best_score = float(items[0]["score"]) if items else 0.0

    if not items or best_score < float(min_best_score):
        return KBAskResult(
            refused=True,
            answer=(
                "I can’t answer that from the transcript I have. "
                "Try asking a more specific question, or embed a different video/pack."
            ),
            model=llm_model,
            citations=[],
            retrieval={
                "study_pack_id": study_pack_id,
                "query": q,
                "limit": int(limit),
                "hybrid": bool(hybrid),
                "min_best_score": float(min_best_score),
                "best_score": float(best_score),
                "retrieved": len(items),
                "reason": "insufficient_evidence",
            },
        )

    # Build citations (top_k only)
    citations: List[KBCitation] = []
    for it in items[:top_k]:
        citations.append(
            KBCitation(
                chunk_id=int(it["chunk_id"]),
                idx=int(it["idx"]),
                start_sec=float(it["start_sec"]),
                end_sec=float(it["end_sec"]),
                text=str(it["text"]),
                score=float(it["score"]),
            )
        )

    # Keep prompt small to avoid slow generations/timeouts
    max_chars_per_chunk = int(os.getenv("KB_QA_MAX_CHARS_PER_CHUNK", "700"))

    ctx_lines: List[str] = []
    for i, c in enumerate(citations, start=1):
        ctx_lines.append(
            f"[{i}] (chunk_id={c.chunk_id}, idx={c.idx}, t={c.start_sec:.2f}-{c.end_sec:.2f}s, score={c.score:.3f})\n"
            f"{_clip(c.text, max_chars_per_chunk)}"
        )

    prompt = f"""You are a study assistant. Answer the question ONLY using the provided transcript excerpts.

Rules:
- If the excerpts do not contain the answer, say you don't know and explain what's missing.
- Every factual claim MUST be supported by citations like [1] or [1][2].
- Do not invent information not present in the excerpts.
- Keep the answer concise (4-8 sentences max).

Question:
{q}

Transcript excerpts:
{chr(10).join(ctx_lines)}

Answer (with citations):
"""

    try:
        answer = _ollama_generate(base_url=base_url, model=llm_model, prompt=prompt)
    except Exception as e:
        # Fail safe: we still return citations + retrieval context
        return KBAskResult(
            refused=True,
            answer=f"I couldn’t generate an answer due to an LLM error: {e}",
            model=llm_model,
            citations=citations,
            retrieval={
                "study_pack_id": study_pack_id,
                "query": q,
                "limit": int(limit),
                "hybrid": bool(hybrid),
                "min_best_score": float(min_best_score),
                "best_score": float(best_score),
                "retrieved": len(items),
                "used": len(citations),
                "reason": "ollama_error",
            },
        )

    return KBAskResult(
        refused=False,
        answer=answer,
        model=llm_model,
        citations=citations,
        retrieval={
            "study_pack_id": study_pack_id,
            "query": q,
            "limit": int(limit),
            "hybrid": bool(hybrid),
            "min_best_score": float(min_best_score),
            "best_score": float(best_score),
            "retrieved": len(items),
            "used": len(citations),
        },
    )