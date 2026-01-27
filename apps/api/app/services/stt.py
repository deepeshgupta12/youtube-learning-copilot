# apps/api/app/services/stt.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from faster_whisper import WhisperModel


@dataclass
class STTResult:
    language: str
    segments: list[dict[str, Any]]  # each: {text, start, duration}


_MODEL: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """
    Keep a single model instance per worker process.
    """
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    # Reasonable defaults for local Mac CPU.
    # You can tune these later via env vars without touching code.
    model_size = os.getenv("YLC_WHISPER_MODEL", "base")  # tiny/base/small/medium/large-v3
    device = os.getenv("YLC_WHISPER_DEVICE", "cpu")      # cpu
    compute_type = os.getenv("YLC_WHISPER_COMPUTE", "int8")  # int8 is fast on CPU

    _MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _MODEL


def transcribe_audio(
    audio_path: str,
    *,
    language: str | None = None,
) -> STTResult:
    """
    Transcribe audio using faster-whisper and return timestamped segments in the
    SAME shape used by your transcript pipeline: [{text, start, duration}, ...]
    """
    model = _get_model()

    segments_iter, info = model.transcribe(
        audio_path,
        language=language,           # optional hint
        vad_filter=True,             # good default to reduce empty/noise segments
        beam_size=5,
    )

    segs: list[dict[str, Any]] = []
    for s in segments_iter:
        txt = (s.text or "").strip()
        if not txt:
            continue
        start = float(s.start)
        end = float(s.end)
        dur = float(max(0.0, end - start))
        segs.append({"text": txt, "start": start, "duration": dur})

    used_lang = (info.language or "").strip() if info else ""
    if not used_lang:
        used_lang = language or "unknown"

    return STTResult(language=used_lang, segments=segs)