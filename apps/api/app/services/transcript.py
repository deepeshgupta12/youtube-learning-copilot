import json
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter


class TranscriptNotFound(Exception):
    pass


def fetch_youtube_transcript(video_id: str, language: str | None = None) -> dict[str, Any]:
    """
    Returns:
      {
        "segments": [{"text": "...", "start": 12.3, "duration": 3.2}, ...],
        "text": "full transcript text...",
        "language": "en"
      }
    """
    try:
        if language:
            segments = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
            used_lang = language
        else:
            # will pick an available transcript automatically
            segments = YouTubeTranscriptApi.get_transcript(video_id)
            used_lang = None
    except Exception as e:
        raise TranscriptNotFound(str(e)) from e

    formatter = TextFormatter()
    text = formatter.format_transcript(segments).strip()

    return {
        "segments": segments,
        "text": text,
        "language": used_lang,
    }


def dumps_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
