import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class YouTubeSettings:
    # Optional: path to cookies.txt (Netscape format). Helps bypass anon blocks.
    cookies_file: str | None = os.getenv("YOUTUBE_COOKIES_FILE")

    # Optional: proxy URL, e.g. http://127.0.0.1:7890
    proxy_url: str | None = os.getenv("YOUTUBE_PROXY_URL")

    # Retry knobs
    max_retries: int = int(os.getenv("YOUTUBE_MAX_RETRIES", "3"))
    backoff_sec: float = float(os.getenv("YOUTUBE_BACKOFF_SEC", "1.5"))

    # Whether to try yt-dlp fallback if transcript_api fails
    enable_ytdlp_fallback: bool = os.getenv("YOUTUBE_ENABLE_YTDLP_FALLBACK", "1") == "1"


youtube_settings = YouTubeSettings()
