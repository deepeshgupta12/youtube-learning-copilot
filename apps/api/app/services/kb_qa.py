# apps/api/app/services/kb_qa.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.kb_search import kb_search_chunks


def _kb_search_chunks_compat(
    db: Session,
    study_pack_id: int,
    *,
    question: str,
    limit: int,
    model: str,
    hybrid: bool,
) -> List[Dict[str, Any]]:
    """
    Compatibility wrapper so we never crash on param-name mismatch.

    Tries:
      kb_search_chunks(..., q=...)
      kb_search_chunks(..., query=...)
      kb_search_chunks(db, study_pack_id, question, ...)  (positional)
    """
    # 1) Newer style: q=
    try:
        return kb_search_chunks(
            db,
            study_pack_id,
            q=question,
            limit=limit,
            model=model,
            hybrid=hybrid,
        )
    except TypeError:
        pass

    # 2) Older style: query=
    try:
        return kb_search_chunks(
            db,
            study_pack_id,
            query=question,
            limit=limit,
            model=model,
            hybrid=hybrid,
        )
    except TypeError:
        pass

    # 3) Positional fallback
    return kb_search_chunks(
        db,
        study_pack_id,
        question,
        limit=limit,
        model=model,
        hybrid=hybrid,
    )


def _ollama_chat(
    *,
    prompt: str,
    system: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> str:
    """
    Minimal Ollama chat client (no dependency on your ollama_client.py impl).
    Uses:
      POST {OLLAMA_BASE_URL}/api/chat
    """
    base_url = getattr(settings, "ollama_base_url", "http://localhost:11434").rstrip("/")
    model_name = model or getattr(settings, "ollama_model", "qwen2.5:7b-instruct")

    url = f"{base_url}/api/chat"
    payload = {
        "model": model_name,
        "stream": False,
        "options": {"temperature": float(temperature)},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }

    with httpx.Client(timeout=120) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()

    # Ollama returns {"message":{"role":"assistant","content":"..."}}
    msg = (data or {}).get("message") or {}
    return (msg.get("content") or "").strip()


def ask_grounded(
    db: Session,
    *,
    study_pack_id: int,
    question: str,
    model: Optional[str] = None,  # <-- NEW: alias for embed_model (back-compat)
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    llm_model: Optional[str] = None,
    limit: int = 6,
    hybrid: bool = True,
    min_score: float = 0.35,
    min_best_score: Optional[float] = None,  # <-- NEW alias
) -> Dict[str, Any]:
    """
    Grounded Q&A:
    - retrieve chunks from KB
    - if retrieval empty/weak -> refusal
    - otherwise answer using Ollama, constrained to chunks
    - return citations with timestamps
    """
    question = (question or "").strip()
    if not question:
        return {
            "ok": True,
            "study_pack_id": study_pack_id,
            "question": question,
            "answer": "",
            "refusal": True,
            "refusal_reason": "Empty question.",
            "citations": [],
            "used_chunks": [],
        }
    # Backward-compat: allow callers to pass model=...
    if model:
        embed_model = model
    if min_best_score is not None:
        min_score = float(min_best_score)

    items = _kb_search_chunks_compat(
        db,
        study_pack_id,
        question=question,
        limit=limit,
        model=embed_model,
        hybrid=hybrid,
    )

    if not items:
        return {
            "ok": True,
            "study_pack_id": study_pack_id,
            "question": question,
            "answer": "Not in this video.",
            "refusal": True,
            "refusal_reason": "No relevant transcript chunks retrieved.",
            "citations": [],
            "used_chunks": [],
        }

    # Score gate (assumes kb_search returns `score` in [0..1] where higher is better)
    best_score = float(items[0].get("score") or 0.0)
    if best_score < float(min_score):
        return {
            "ok": True,
            "study_pack_id": study_pack_id,
            "question": question,
            "answer": "Not in this video.",
            "refusal": True,
            "refusal_reason": f"Low retrieval confidence (best_score={best_score:.3f} < {min_score:.3f}).",
            "citations": [],
            "used_chunks": items,
        }

    # Build context with explicit citations
    context_lines: List[str] = []
    citations: List[Dict[str, Any]] = []
    for i, it in enumerate(items, start=1):
        chunk_id = int(it["chunk_id"])
        start_sec = float(it.get("start_sec") or 0.0)
        end_sec = float(it.get("end_sec") or 0.0)
        text = (it.get("text") or "").strip()

        tag = f"[C{i}]"
        context_lines.append(
            f"{tag} chunk_id={chunk_id} time={start_sec:.3f}-{end_sec:.3f}\n{text}"
        )
        citations.append(
            {
                "ref": tag,
                "chunk_id": chunk_id,
                "start_sec": start_sec,
                "end_sec": end_sec,
            }
        )

    system = (
        "You are a strict study assistant.\n"
        "You MUST answer using ONLY the provided transcript chunks.\n"
        "If the answer is not present in the chunks, reply exactly: Not in this video.\n"
        "When you use facts, add citations like [C1], [C2] corresponding to the chunks.\n"
        "Do not invent citations.\n"
    )

    prompt = (
        f"Question:\n{question}\n\n"
        f"Transcript chunks:\n\n" + "\n\n".join(context_lines) + "\n\n"
        "Answer (with citations):"
    )

    answer = _ollama_chat(prompt=prompt, system=system, model=llm_model, temperature=0.2)

    refusal = answer.strip().lower() == "not in this video."
    used = [] if refusal else citations

    return {
        "ok": True,
        "study_pack_id": study_pack_id,
        "question": question,
        "answer": answer,
        "refusal": refusal,
        "refusal_reason": None if not refusal else "Model indicated answer not supported by retrieved chunks.",
        "citations": used,
        "used_chunks": items,
    }