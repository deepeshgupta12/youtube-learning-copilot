import re
from urllib.parse import urlparse, parse_qs


_YT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def extract_youtube_video_id(url: str) -> str | None:
    """
    Supports:
    - https://www.youtube.com/watch?v=VIDEOID
    - https://youtu.be/VIDEOID
    - https://www.youtube.com/shorts/VIDEOID
    """
    try:
        u = urlparse(url)
    except Exception:
        return None

    host = (u.netloc or "").lower()
    path = (u.path or "").strip("/")

    # youtu.be/VIDEOID
    if "youtu.be" in host:
        vid = path.split("/")[0] if path else ""
        return vid if _YT_ID_RE.match(vid) else None

    # youtube.com/watch?v=VIDEOID
    if "youtube.com" in host:
        if path == "watch":
            q = parse_qs(u.query or "")
            vid = (q.get("v", [""])[0]).strip()
            return vid if _YT_ID_RE.match(vid) else None

        # youtube.com/shorts/VIDEOID
        if path.startswith("shorts/"):
            vid = path.split("/")[1] if len(path.split("/")) > 1 else ""
            return vid if _YT_ID_RE.match(vid) else None

        # youtube.com/embed/VIDEOID
        if path.startswith("embed/"):
            vid = path.split("/")[1] if len(path.split("/")) > 1 else ""
            return vid if _YT_ID_RE.match(vid) else None

    return None
