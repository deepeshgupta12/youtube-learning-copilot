from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class STTError(Exception):
    pass


@dataclass
class STTSegment:
    text: str
    start: float
    end: float


def transcribe_faster_whisper(
    wav_path: Path,
    *,
    language: str | None = None,
    model_size: str = "small",
    compute_type: str = "int8",
) -> dict[str, Any]:
    """
    Returns:
      {
        "segments": [{"text":..., "start":..., "duration":...}, ...],
        "text": "...",
        "language": "en" | "unknown" | provided
      }
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        raise STTError(f"faster-whisper not installed/usable: {e}") from e

    try:
        model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    except Exception as e:
        raise STTError(f"failed to load faster-whisper model '{model_size}': {e}") from e

    try:
        segments_iter, info = model.transcribe(
            str(wav_path),
            language=language if language else None,
            vad_filter=True,
            beam_size=5,
        )
    except Exception as e:
        raise STTError(f"transcribe failed: {e}") from e

    segs: list[dict[str, Any]] = []
    parts: list[str] = []

    for s in segments_iter:
        txt = (getattr(s, "text", "") or "").strip()
        start = float(getattr(s, "start", 0.0) or 0.0)
        end = float(getattr(s, "end", start) or start)
        if not txt:
            continue
        if end < start:
            end = start
        segs.append({"text": txt, "start": start, "duration": max(0.0, end - start)})
        parts.append(txt)

    full_text = " ".join(parts).strip()
    if not full_text:
        raise STTError("STT produced empty transcript text")

    used_lang = getattr(info, "language", None) or language or "unknown"
    return {"segments": segs, "text": full_text, "language": used_lang}