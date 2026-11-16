"""Search YouTube from the page, with yt-dlp, and pass on the results'
pictures, so the page loads nothing from anywhere but this app."""

import re
import urllib.request

import yt_dlp

from .tube import TubeError

RESULTS = 12
MAX_QUERY_LENGTH = 200
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Running or about to start: neither can be downloaded as a song.
LIVE = {"is_live", "is_upcoming", "post_live"}
THUMBNAIL_URL = "https://i.ytimg.com/vi/{}/mqdefault.jpg"
MAX_THUMBNAIL_BYTES = 512 * 1024


def search(query) -> list[dict]:
    """The first videos YouTube finds for `query`. Only their list is fetched,
    nothing is downloaded, so it takes a second or two."""
    if not isinstance(query, str) or not query.strip():
        raise TubeError("Type something to search for", 400)
    query = " ".join(query.split())[:MAX_QUERY_LENGTH]
    options = {"extract_flat": True, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{RESULTS}:{query}", download=False)
    except yt_dlp.utils.YoutubeDLError as error:
        message = str(error).removeprefix("ERROR: ").strip()
        raise TubeError(message or "The search did not work", 502) from None

    results = []
    for entry in info.get("entries") or []:
        video_id = entry.get("id") or ""
        if not VIDEO_ID.match(video_id) or entry.get("live_status") in LIVE:
            continue
        results.append(
            {
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": entry.get("title") or "",
                "artist": entry.get("channel") or entry.get("uploader") or "",
                "duration": entry.get("duration"),
                "thumbnail": f"thumbnails/{video_id}",
            }
        )
    return results


def thumbnail(video_id: str) -> bytes | None:
    """A result's picture, fetched here: the page only loads from this app."""
    if not VIDEO_ID.match(video_id):
        return None
    try:
        with urllib.request.urlopen(THUMBNAIL_URL.format(video_id), timeout=10) as response:
            data = response.read(MAX_THUMBNAIL_BYTES + 1)
    except OSError:
        return None
    return data if len(data) <= MAX_THUMBNAIL_BYTES else None
