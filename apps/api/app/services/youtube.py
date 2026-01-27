import json
import re
import subprocess
from urllib.parse import urlparse, parse_qs


_YT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_PL_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,256}$")


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
            parts = path.split("/")
            vid = parts[1] if len(parts) > 1 else ""
            return vid if _YT_ID_RE.match(vid) else None

        # youtube.com/embed/VIDEOID
        if path.startswith("embed/"):
            parts = path.split("/")
            vid = parts[1] if len(parts) > 1 else ""
            return vid if _YT_ID_RE.match(vid) else None

    return None


def extract_youtube_playlist_id(url: str) -> str | None:
    """
    Supports:
    - https://www.youtube.com/playlist?list=PLAYLISTID
    - https://www.youtube.com/watch?v=VIDEOID&list=PLAYLISTID
    - https://youtu.be/VIDEOID?list=PLAYLISTID
    """
    try:
        u = urlparse(url)
    except Exception:
        return None

    host = (u.netloc or "").lower()
    path = (u.path or "").strip("/")
    q = parse_qs(u.query or "")

    # Most common: list=...
    pl = (q.get("list", [""])[0]).strip()
    if pl and _PL_ID_RE.match(pl):
        return pl

    # Some playlist URLs may not carry query (rare), so try path heuristics
    if "youtube.com" in host and path == "playlist":
        pl = (q.get("list", [""])[0]).strip()
        return pl if pl and _PL_ID_RE.match(pl) else None

    return None


def fetch_playlist_metadata(url: str, *, max_items: int = 200) -> dict:
    """
    Uses yt-dlp (must be installed) to fetch playlist metadata quickly.

    Returns:
      {
        "playlist_id": str,
        "playlist_title": str|None,
        "entries": [{"video_id": str, "title": str|None, "index": int}]
      }
    """
    # yt-dlp --flat-playlist keeps it fast (no per-video deep fetch)
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        "--ignore-errors",
        url,
    ]

    try:
        p = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Install it (pipx/brew/pip) and ensure it is on PATH.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timed out while fetching playlist metadata.")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"yt-dlp failed: {stderr or 'unknown error'}")

    raw = (p.stdout or "").strip()
    if not raw:
        raise RuntimeError("yt-dlp returned empty output for playlist metadata.")

    try:
        data = json.loads(raw)
    except Exception:
        raise RuntimeError("Could not parse yt-dlp JSON output for playlist metadata.")

    playlist_id = (data.get("id") or "").strip() or (extract_youtube_playlist_id(url) or "")
    if not playlist_id:
        raise RuntimeError("Could not resolve playlist_id from yt-dlp output or URL.")

    playlist_title = (data.get("title") or None)

    entries = []
    raw_entries = data.get("entries") or []
    idx = 0
    for e in raw_entries:
        if not isinstance(e, dict):
            continue
        vid = (e.get("id") or "").strip()
        if not vid or not _YT_ID_RE.match(vid):
            continue
        idx += 1
        entries.append(
            {
                "video_id": vid,
                "title": (e.get("title") or None),
                "index": idx,
            }
        )
        if max_items and len(entries) >= max_items:
            break

    if not entries:
        raise RuntimeError("Playlist has no usable video entries (or yt-dlp could not read entries).")

    return {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "entries": entries,
    }


def build_video_url(video_id: str, *, playlist_id: str | None = None, playlist_index: int | None = None) -> str:
    base = f"https://www.youtube.com/watch?v={video_id}"
    if playlist_id:
        base += f"&list={playlist_id}"
    if playlist_index is not None:
        base += f"&index={playlist_index}"
    return base