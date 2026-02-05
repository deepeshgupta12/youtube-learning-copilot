from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.study_pack import StudyPack
from app.services.kb_search import kb_search_chunks
from app.services.ollama_client import OllamaClient


@dataclass
class Citation:
    chunk_id: int
    idx: int
    start_sec: float
    end_sec: float
    text: str
    score: float


@dataclass
class AskResult:
    refused: bool
    answer: str
    citations: List[Citation]
    model: str
    retrieval: Dict[str, Any]


def _build_context(citations: List[Citation], max_chars_per_chunk: int = 800) -> str:
    """
    Build a context block that is easy for the LLM to cite.
    We keep chunk text trimmed but still meaningful.
    """
    lines: List[str] = []
    for c in citations:
        t = c.text.strip()
        if len(t) > max_chars_per_chunk:
            t = t[: max_chars_per_chunk].rstrip() + "…"
        lines.append(
            f"[chunk_id={c.chunk_id} idx={c.idx} time={c.start_sec:.3f}-{c.end_sec:.3f}]\n{t}\n"
        )
    return "\n".join(lines).strip()


def _qa_system_prompt() -> str:
    return (
        "You are a strict study assistant.\n"
        "You MUST answer using ONLY the provided transcript chunks.\n"
        "If the chunks do not contain the answer, respond exactly with:\n"
        "NOT_IN_VIDEO\n"
        "Do not use outside knowledge.\n"
        "Do not speculate.\n"
    )


def _qa_user_prompt(question: str, context: str) -> str:
    return (
        "Transcript chunks:\n"
        f"{context}\n\n"
        "User question:\n"
        f"{question}\n\n"
        "Rules:\n"
        "1) Answer ONLY from transcript chunks.\n"
        "2) If answer is not explicitly supported, output: NOT_IN_VIDEO\n"
        "3) Keep answer concise and factual.\n"
    )


def _should_refuse(citations: List[Citation], min_best_score: float) -> bool:
    if not citations:
        return True
    best = max(c.score for c in citations)
    return best < min_best_score


def ask_grounded(
    db: Session,
    study_pack_id: int,
    question: str,
    model: Optional[str] = None,
    limit: int = 6,
    hybrid: bool = True,
    min_best_score: float = 0.52,
) -> AskResult:
    question = (question or "").strip()
    if not question:
        return AskResult(
            refused=True,
            answer="Not covered in this video.",
            citations=[],
            model=model or "",
            retrieval={"reason": "empty_question"},
        )

    sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
    if not sp:
        return AskResult(
            refused=True,
            answer="Not covered in this video.",
            citations=[],
            model=model or "",
            retrieval={"reason": "study_pack_not_found"},
        )

    # Use default embedding model if none passed (same default used in kb_search)
    embed_model = model or "sentence-transformers/all-MiniLM-L6-v2"

    # Retrieve top chunks
    items = kb_search_chunks(
        db=db,
        study_pack_id=study_pack_id,
        q=question,
        model=embed_model,
        limit=limit,
        hybrid=hybrid,
    )

    citations: List[Citation] = []
    for it in items:
        citations.append(
            Citation(
                chunk_id=int(it["chunk_id"]),
                idx=int(it["idx"]),
                start_sec=float(it["start_sec"]),
                end_sec=float(it["end_sec"]),
                text=str(it["text"] or ""),
                score=float(it.get("score") or 0.0),
            )
        )

    # Early refusal if retrieval too weak
    if _should_refuse(citations, min_best_score=min_best_score):
        return AskResult(
            refused=True,
            answer="Not covered in this video.",
            citations=[],
            model=embed_model,
            retrieval={
                "hybrid": hybrid,
                "limit": limit,
                "min_best_score": min_best_score,
                "best_score": max((c.score for c in citations), default=0.0),
                "retrieved": len(citations),
            },
        )

    context = _build_context(citations)

    # Call Ollama
    base_url = getattr(settings, "ollama_base_url", None) or "http://localhost:11434"
    llm_model = getattr(settings, "ollama_model", None) or "qwen2.5:7b-instruct"
    client = OllamaClient(base_url=base_url, timeout_s=180.0)

    sys_prompt = _qa_system_prompt()
    user_prompt = _qa_user_prompt(question, context)

    out = client.generate(model=llm_model, prompt=user_prompt, system=sys_prompt, temperature=0.2)
    text = (out.text or "").strip()

    if not text:
        return AskResult(
            refused=True,
            answer="Not covered in this video.",
            citations=[],
            model=embed_model,
            retrieval={"reason": "empty_llm_output"},
        )

    if "NOT_IN_VIDEO" in text:
        return AskResult(
            refused=True,
            answer="Not covered in this video.",
            citations=[],
            model=embed_model,
            retrieval={"reason": "llm_refused"},
        )

    # Success: return answer + citations
    return AskResult(
        refused=False,
        answer=text,
        citations=citations,
        model=embed_model,
        retrieval={
            "hybrid": hybrid,
            "limit": limit,
            "min_best_score": min_best_score,
            "best_score": max((c.score for c in citations), default=0.0),
            "retrieved": len(citations),
        },
    )