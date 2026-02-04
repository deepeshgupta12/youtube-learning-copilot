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


# -----------------------------
# Cleaning + normalization (V1.4.6)
# -----------------------------
_DEFAULT_DROP_BRACKETED = os.getenv("YLC_DROP_BRACKETED_NOISE", "1").strip() != "0"
_DEFAULT_MIN_SEG_DUR = float(os.getenv("YLC_MIN_SEG_DUR_SEC", "0.25"))  # tiny segments get merged
_DEFAULT_MIN_SEG_CHARS = int(os.getenv("YLC_MIN_SEG_CHARS", "4"))
_DEFAULT_DEDUPE_WINDOW = int(os.getenv("YLC_DEDUPE_WINDOW", "1"))  # consecutive-only by default

# Rolling-caption overlap stripping
_DEFAULT_OVERLAP_MAX_WORDS = int(os.getenv("YLC_OVERLAP_MAX_WORDS", "18"))
_DEFAULT_OVERLAP_MIN_WORDS = int(os.getenv("YLC_OVERLAP_MIN_WORDS", "4"))

_NOISE_WORDS = r"(music|applause|laughter|intro|outro|silence|sfx|sound effects?)"
_NOISE_FULL_RE = re.compile(rf"^\s*\[{_NOISE_WORDS}\]\s*$", re.IGNORECASE)
_NOISE_PREFIX_RE = re.compile(rf"^\s*(?:\[{_NOISE_WORDS}\]\s*)+", re.IGNORECASE)

_word_re = re.compile(r"[A-Za-z0-9']+")


def _words(s: str) -> list[str]:
    return [w.lower() for w in _word_re.findall(s or "")]


def _collapse_consecutive_phrase_repeats(
    text: str,
    *,
    min_words: int = 3,
    max_words: int = 10,
    max_passes: int = 6,
) -> str:
    """
    Collapse consecutive repeated phrases inside the same segment.

    Example:
      "structure is what it's made up of structure is what it's made up of"
      -> "structure is what it's made up of"

    Useful when a single caption line duplicates itself.
    """
    original = text
    t = " ".join((text or "").split()).strip()
    if not t:
        return t

    toks = t.split()
    if len(toks) < min_words * 2:
        return t

    for _ in range(max_passes):
        changed = False
        n = len(toks)

        i = 0
        out: list[str] = []
        while i < n:
            best_k = 0

            for k in range(min(max_words, (n - i) // 2), min_words - 1, -1):
                a = toks[i : i + k]
                b = toks[i + k : i + 2 * k]
                if _words(" ".join(a)) == _words(" ".join(b)):
                    best_k = k
                    break

            if best_k > 0:
                phrase = toks[i : i + best_k]
                out.extend(phrase)
                i += best_k

                while i + best_k <= n and _words(" ".join(toks[i : i + best_k])) == _words(" ".join(phrase)):
                    i += best_k

                changed = True
                continue

            out.append(toks[i])
            i += 1

        toks = out
        if not changed:
            break

    collapsed = " ".join(toks).strip()
    return collapsed if collapsed else original


def _normalize_space(s: str) -> str:
    s = (s or "").replace("\u200b", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_noise_prefix(txt: str) -> str:
    if not _DEFAULT_DROP_BRACKETED:
        return txt
    return _NOISE_PREFIX_RE.sub("", txt).strip()


def _is_noise_text(txt: str) -> bool:
    if not txt:
        return True
    if _DEFAULT_DROP_BRACKETED and _NOISE_FULL_RE.match(txt.strip()):
        return True
    return False


def _canon_text(txt: str) -> str:
    return _normalize_space(txt).lower()


def _strip_leading_word_overlap(
    prev_text: str,
    cur_text: str,
    *,
    max_words: int,
    min_words: int,
) -> str:
    """
    Rolling captions often repeat the tail of the previous caption at the head of the next.
    We remove the largest word-overlap:
      suffix(prev_words, k) == prefix(cur_words, k)
    for k in [max_words..min_words].

    Returns possibly-trimmed cur_text.
    """
    if not prev_text or not cur_text:
        return cur_text

    pw = _words(prev_text)
    cw = _words(cur_text)
    if not pw or not cw:
        return cur_text

    max_k = min(max_words, len(pw), len(cw))
    if max_k < min_words:
        return cur_text

    overlap_k = 0
    for k in range(max_k, min_words - 1, -1):
        if pw[-k:] == cw[:k]:
            overlap_k = k
            break

    if overlap_k <= 0:
        return cur_text

    # Trim from the ORIGINAL tokenization of cur_text (preserve punctuation-ish spacing)
    # We do a simple split trim; good enough because subtitles are mostly plain words.
    cur_tokens = (cur_text or "").split()
    if len(cur_tokens) <= overlap_k:
        return ""

    trimmed = " ".join(cur_tokens[overlap_k:]).strip()
    return trimmed


def _proxy_dict(proxy_url: str | None) -> dict | None:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def _vtt_timestamp_to_seconds(ts: str) -> float:
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


def clean_segments(
    segments: list[dict[str, Any]],
    *,
    min_dur_sec: float = _DEFAULT_MIN_SEG_DUR,
    min_chars: int = _DEFAULT_MIN_SEG_CHARS,
    dedupe_window: int = _DEFAULT_DEDUPE_WINDOW,
    overlap_max_words: int = _DEFAULT_OVERLAP_MAX_WORDS,
    overlap_min_words: int = _DEFAULT_OVERLAP_MIN_WORDS,
) -> list[dict[str, Any]]:
    """
    Clean + normalize transcript segments:
    - normalize spaces
    - strip leading bracketed noise prefix like "[Music] ..."
    - drop pure noise tokens like "[Music]"
    - strip rolling-caption overlap vs previous kept segment (word-based)
    - collapse consecutive repeated phrases inside a segment
    - collapse consecutive duplicates (rolling dedupe)
    - merge tiny segments into previous segment
    Returns segments in schema: {text, start, duration}
    """
    cleaned: list[dict[str, Any]] = []
    recent: list[str] = []

    for seg in segments or []:
        raw_txt = (seg.get("text") or "").strip()
        txt = _normalize_space(raw_txt)
        if not txt:
            continue

        # strip noise prefix (handles "[Music] hello")
        txt = _strip_noise_prefix(txt)
        if not txt:
            continue

        # drop pure bracket noise (handles "[Music]")
        if _is_noise_text(txt):
            continue

        start = float(seg.get("start") or 0.0)
        duration = float(seg.get("duration") or 0.0)
        duration = max(0.0, duration)

        # NEW: rolling-caption overlap stripping against previous kept segment
        if cleaned:
            prev_txt = cleaned[-1].get("text") or ""
            txt = _strip_leading_word_overlap(
                prev_txt,
                txt,
                max_words=overlap_max_words,
                min_words=overlap_min_words,
            )
            txt = _normalize_space(txt)
            if not txt:
                # nothing new in this caption; extend timing coverage on last segment
                last = cleaned[-1]
                last_end = float(last["start"]) + float(last["duration"])
                this_end = start + duration
                if this_end > last_end:
                    last["duration"] = float(max(0.0, this_end - float(last["start"])))
                continue

        # Collapse phrase repeats inside the SAME segment (rare but happens)
        txt = _collapse_consecutive_phrase_repeats(txt, min_words=3, max_words=10, max_passes=6)
        txt = _normalize_space(txt)
        if not txt:
            continue

        canon = _canon_text(txt)

        # rolling dedupe (consecutive by default)
        if dedupe_window > 0 and canon and canon in recent[-dedupe_window:]:
            if cleaned:
                last = cleaned[-1]
                last_end = float(last["start"]) + float(last["duration"])
                this_end = start + duration
                if this_end > last_end:
                    last["duration"] = float(max(0.0, this_end - float(last["start"])))
            continue

        # merge tiny segments into previous
        if cleaned and (duration < min_dur_sec or len(txt) < min_chars):
            last = cleaned[-1]
            last_txt = _normalize_space(last.get("text") or "")

            if _canon_text(last_txt) != canon:
                last["text"] = (last_txt + " " + txt).strip()

            last_end = float(last["start"]) + float(last["duration"])
            this_end = start + duration
            if this_end > last_end:
                last["duration"] = float(max(0.0, this_end - float(last["start"])))

            recent.append(canon)
            continue

        cleaned.append({"text": txt, "start": float(start), "duration": float(duration)})
        recent.append(canon)

    return cleaned


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

    return {"segments": segments, "text": text, "language": used_lang or language or "unknown", "method": "captions"}


def _fetch_with_ytdlp_subs(video_id: str, language: str | None) -> dict[str, Any]:
    try:
        import webvtt  # type: ignore
    except Exception as e:
        raise TranscriptNotFound(f"webvtt-py not available: {e}") from e

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as td:
        outtmpl = str(Path(td) / "%(id)s.%(ext)s")

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
            txt = _normalize_space(txt)
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
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = str(Path(out_dir) / "%(id)s.%(ext)s")

    args = ["yt-dlp", "-f", "bestaudio/best", "-o", outtmpl, url]

    if youtube_settings.cookies_file:
        args.extend(["--cookies", youtube_settings.cookies_file])

    if youtube_settings.proxy_url:
        args.extend(["--proxy", youtube_settings.proxy_url])

    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise TranscriptNotFound(f"yt-dlp audio failed: {p.stderr.strip() or p.stdout.strip()}")

    candidates = list(Path(out_dir).glob(f"{video_id}.*"))
    if not candidates:
        raise TranscriptNotFound("yt-dlp audio succeeded but could not find output audio file")

    return str(sorted(candidates, key=lambda x: x.stat().st_size, reverse=True)[0])


def _normalize_to_wav(input_audio_path: str, out_dir: str) -> str:
    ffmpeg = _ensure_ffmpeg()
    out_wav = str(Path(out_dir) / "audio_16k_mono.wav")

    args = [ffmpeg, "-y", "-i", input_audio_path, "-vn", "-ac", "1", "-ar", "16000", out_wav]
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise TranscriptNotFound(f"ffmpeg convert failed: {p.stderr.strip() or p.stdout.strip()}")

    return out_wav


def _fetch_with_stt(video_id: str, language: str | None) -> dict[str, Any]:
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
            return _fetch_with_ytdlp_subs(video_id, language)
        except Exception as e:
            last_err = e

    if getattr(youtube_settings, "enable_stt_fallback", True):
        try:
            return _fetch_with_stt(video_id, language)
        except Exception as e:
            last_err = e

    raise TranscriptNotFound(str(last_err) if last_err else "Transcript fetch failed")