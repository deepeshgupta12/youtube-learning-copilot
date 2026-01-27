from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class AudioDownloadError(Exception):
    pass


def download_youtube_audio(video_id: str, *, cookies_file: str | None = None, proxy_url: str | None = None) -> Path:
    """
    Downloads best available audio for a YouTube video using yt-dlp.
    Returns the downloaded file path.

    We download the audio container as-is (m4a/webm/etc) and let ffmpeg convert later.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    td = tempfile.TemporaryDirectory()
    tmp_dir = Path(td.name)

    # Keep template without extension; yt-dlp will add it.
    outtmpl = str(tmp_dir / f"{video_id}.%(ext)s")

    args = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bestaudio/best",
        "-o",
        outtmpl,
        url,
    ]

    if cookies_file:
        args.extend(["--cookies", cookies_file])
    if proxy_url:
        args.extend(["--proxy", proxy_url])

    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        td.cleanup()
        raise AudioDownloadError(p.stderr.strip() or p.stdout.strip() or "yt-dlp audio download failed")

    # Find the downloaded file (should be exactly one for this id)
    candidates = sorted(tmp_dir.glob(f"{video_id}.*"), key=lambda x: x.stat().st_size, reverse=True)
    if not candidates:
        td.cleanup()
        raise AudioDownloadError("yt-dlp succeeded but no audio file was produced")

    audio_path = candidates[0]

    # Important: keep the tempdir alive by attaching it to the Path object
    # so caller can clean it by calling audio_path._tmp.cleanup()
    setattr(audio_path, "_tmp", td)  # type: ignore[attr-defined]

    return audio_path