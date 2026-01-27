# apps/api/app/services/transcript.py
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from app.core.youtube_settings import youtube_settings
from app.services.stt import transcribe_audio


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


def _segments_to_text(segments: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for seg in segments:
        txt = (seg.get("text") or "").strip()
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()


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

    # transcript_api segments already have: {text, start, duration}
    return {"segments": segments, "text": text, "language": used_lang or language or "unknown", "method": "captions"}


def _fetch_with_ytdlp_subs(video_id: str, language: str | None) -> dict[str, Any]:
    """
    yt-dlp fallback: downloads subtitles (manual or auto) as VTT and parses them.
    Produces segments in {text, start, duration}.
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

        p = subprocess.run(args, capture_output=True, text=True)
        if p.returncode != 0:
            raise TranscriptNotFound(f"yt-dlp subs failed: {p.stderr.strip() or p.stdout.strip()}")

        vtts = list(Path(td).glob("*.vtt"))
        if not vtts:
            raise TranscriptNotFound("yt-dlp succeeded but no .vtt subtitles found")

        vtt_path = sorted(vtts, key=lambda x: x.stat().st_size, reverse=True)[0]

        segments: list[dict[str, Any]] = []
        for caption in webvtt.read(str(vtt_path)):
            start = _vtt_timestamp_to_seconds(caption.start)
            end = _vtt_timestamp_to_seconds(caption.end)
            txt = (caption.text or "").replace("\n", " ").strip()
            if not txt:
                continue
            segments.append({"text": txt, "start": float(start), "duration": float(max(0.0, end - start))})

        text = _segments_to_text(segments)
        if not text:
            raise TranscriptNotFound("Parsed VTT but transcript text is empty")

        used_lang = language or "unknown"
        return {"segments": segments, "text": text, "language": used_lang, "method": "ytdlp_subs"}


def _ensure_ffmpeg() -> str:
    ffmpeg = os.getenv("FFMPEG_BIN", "ffmpeg")
    p = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True)
    if p.returncode != 0:
        raise TranscriptNotFound("ffmpeg not found or not working. Install via brew install ffmpeg.")
    return ffmpeg


def _download_audio_with_ytdlp(video_id: str, out_dir: str) -> str:
    """
    Download best audio track only to out_dir.
    Returns downloaded file path.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = str(Path(out_dir) / "%(id)s.%(ext)s")

    args = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "-o",
        outtmpl,
        url,
    ]

    if youtube_settings.cookies_file:
        args.extend(["--cookies", youtube_settings.cookies_file])

    if youtube_settings.proxy_url:
        args.extend(["--proxy", youtube_settings.proxy_url])

    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise TranscriptNotFound(f"yt-dlp audio failed: {p.stderr.strip() or p.stdout.strip()}")

    # find the downloaded file (video_id.*)
    candidates = list(Path(out_dir).glob(f"{video_id}.*"))
    if not candidates:
        raise TranscriptNotFound("yt-dlp audio succeeded but could not find output audio file")

    # pick largest
    audio_path = str(sorted(candidates, key=lambda x: x.stat().st_size, reverse=True)[0])
    return audio_path


def _normalize_to_wav(input_audio_path: str, out_dir: str) -> str:
    """
    Normalize/convert to 16kHz mono wav for STT.
    """
    ffmpeg = _ensure_ffmpeg()
    out_wav = str(Path(out_dir) / "audio_16k_mono.wav")

    # -vn remove video; -ac 1 mono; -ar 16000 sample rate
    args = [
        ffmpeg,
        "-y",
        "-i",
        input_audio_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        out_wav,
    ]
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise TranscriptNotFound(f"ffmpeg convert failed: {p.stderr.strip() or p.stdout.strip()}")

    return out_wav


def _fetch_with_stt(video_id: str, language: str | None) -> dict[str, Any]:
    """
    Final fallback:
      yt-dlp audio download -> ffmpeg normalize -> faster-whisper transcription
    Returns segments in {text,start,duration}.
    """
    with tempfile.TemporaryDirectory() as td:
        audio_path = _download_audio_with_ytdlp(video_id, td)
        wav_path = _normalize_to_wav(audio_path, td)

        stt = transcribe_audio(wav_path, language=language)
        segments = stt.segments
        text = _segments_to_text(segments)

        if not text:
            raise TranscriptNotFound("STT produced empty transcript")

        return {"segments": segments, "text": text, "language": stt.language, "method": "stt"}


def fetch_youtube_transcript(video_id: str, language: str | None = None) -> dict[str, Any]:
    """
    Main entry:
      1) Try youtube_transcript_api with retries+backoff
      2) Fallback to yt-dlp subtitles (.vtt) if enabled
      3) Fallback to STT (yt-dlp audio + ffmpeg + faster-whisper) if enabled
    """
    last_err: Exception | None = None

    # 1) captions-first
    for attempt in range(1, youtube_settings.max_retries + 1):
        try:
            return _fetch_with_transcript_api(video_id, language)
        except Exception as e:
            last_err = e
            if attempt < youtube_settings.max_retries:
                time.sleep(youtube_settings.backoff_sec * attempt)
            continue

    # 2) yt-dlp subtitles fallback
    if youtube_settings.enable_ytdlp_fallback:
        try:
            return _fetch_with_ytdlp_subs(video_id, language)
        except Exception as e:
            last_err = e

    # 3) STT fallback
    if getattr(youtube_settings, "enable_stt_fallback", True):
        try:
            return _fetch_with_stt(video_id, language)
        except Exception as e:
            last_err = e

    raise TranscriptNotFound(str(last_err) if last_err else "Transcript fetch failed")