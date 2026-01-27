from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class AudioNormalizeError(Exception):
    pass


def normalize_to_wav_16k_mono(input_path: Path) -> Path:
    """
    Convert any audio container to 16kHz mono WAV suitable for STT.
    Returns output wav path (in temp folder).
    """
    td = tempfile.TemporaryDirectory()
    tmp_dir = Path(td.name)

    out_wav = tmp_dir / f"{input_path.stem}.wav"

    args = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        str(out_wav),
    ]

    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        td.cleanup()
        raise AudioNormalizeError(p.stderr.strip() or p.stdout.strip() or "ffmpeg normalize failed")

    setattr(out_wav, "_tmp", td)  # type: ignore[attr-defined]
    return out_wav