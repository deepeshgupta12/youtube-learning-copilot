from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from app.core.youtube_settings import youtube_settings


class TranscriptNotFound(Exception):
    pass


def _proxy_dict(proxy_url: str | None) -> dict | None:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def _vtt_timestamp_to_seconds(ts: str) -> float:
    # 00:01:02.345
    m = re.match(r"(?P<h>\d+):(?P<m>\d+):(?P<s>\d+(?:\.\d+)?)", ts.strip())
    if not m:
        return 0.0
    h = float(m.group("h"))
    mi = float(m.group("m"))
    s = float(m.group("s"))
    return h * 3600.0 + mi * 60.0 + s


def _fetch_with_transcript_api(video_id: str, language: str | None) -> dict[str, Any]:
    proxies = _proxy_dict(youtube_settings.proxy_url)
    cookies = youtube_settings.cookies_file

    if language:
        segments = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=[language],
            proxies=proxies,
            cookies=cookies,
        )
        used_lang = language
    else:
        segments = YouTubeTranscriptApi.get_transcript(
            video_id,
            proxies=proxies,
            cookies=cookies,
        )
        used_lang = None

    text = TextFormatter().format_transcript(segments).strip()
    if not text:
        raise TranscriptNotFound("Transcript empty after fetch (transcript_api)")

    return {"segments": segments, "text": text, "language": used_lang or language or "unknown"}


def _fetch_with_ytdlp(video_id: str, language: str | None) -> dict[str, Any]:
    """
    yt-dlp fallback: downloads subtitles (manual or auto) as VTT and parses them.
    """
    try:
        import webvtt  # type: ignore
    except Exception as e:
        raise TranscriptNotFound(f"webvtt-py not available: {e}") from e

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as td:
        outtmpl = str(Path(td) / "%(id)s.%(ext)s")

        # Prefer requested language, else try en first then any
        sub_langs = language or "en.*"
        args = [
            "yt-dlp",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-format",
            "vtt",
            "--sub-langs",
            sub_langs,
            "-o",
            outtmpl,
            url,
        ]

        if youtube_settings.cookies_file:
            args.extend(["--cookies", youtube_settings.cookies_file])

        if youtube_settings.proxy_url:
            args.extend(["--proxy", youtube_settings.proxy_url])

        # Run yt-dlp
        p = subprocess.run(args, capture_output=True, text=True)
        if p.returncode != 0:
            raise TranscriptNotFound(f"yt-dlp failed: {p.stderr.strip() or p.stdout.strip()}")

        # Find any .vtt in temp dir
        vtts = list(Path(td).glob("*.vtt"))
        if not vtts:
            raise TranscriptNotFound("yt-dlp succeeded but no .vtt subtitles found")

        # Pick the largest VTT as best candidate
        vtt_path = sorted(vtts, key=lambda x: x.stat().st_size, reverse=True)[0]

        segments: list[dict[str, Any]] = []
        full_text_parts: list[str] = []

        for caption in webvtt.read(str(vtt_path)):
            start = _vtt_timestamp_to_seconds(caption.start)
            end = _vtt_timestamp_to_seconds(caption.end)
            txt = (caption.text or "").replace("\n", " ").strip()
            if not txt:
                continue
            segments.append({"text": txt, "start": float(start), "duration": float(max(0.0, end - start))})
            full_text_parts.append(txt)

        text = " ".join(full_text_parts).strip()
        if not text:
            raise TranscriptNotFound("Parsed VTT but transcript text is empty")

        used_lang = language or "unknown"
        return {"segments": segments, "text": text, "language": used_lang}


def fetch_youtube_transcript(video_id: str, language: str | None = None) -> dict[str, Any]:
    """
    Main entry:
      1) Try youtube_transcript_api with retries+backoff
      2) If enabled, fallback to yt-dlp subtitles
    """
    last_err: Exception | None = None

    for attempt in range(1, youtube_settings.max_retries + 1):
        try:
            return _fetch_with_transcript_api(video_id, language)
        except Exception as e:
            last_err = e
            if attempt < youtube_settings.max_retries:
                time.sleep(youtube_settings.backoff_sec * attempt)
            continue

    if youtube_settings.enable_ytdlp_fallback:
        try:
            return _fetch_with_ytdlp(video_id, language)
        except Exception as e:
            raise TranscriptNotFound(str(e)) from e

    raise TranscriptNotFound(str(last_err) if last_err else "Transcript fetch failed")
