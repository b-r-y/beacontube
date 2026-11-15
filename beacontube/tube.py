"""Turns a pasted link into an audio file on this machine, with yt-dlp, and
keeps the last few links played.

The audio is downloaded first and served from the cache: a stream address
from YouTube expires within hours and cannot be seeked reliably."""

import glob
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yt_dlp

HISTORY_LENGTH = 10
MAX_URL_LENGTH = 2048
# Songs that left the history keep their files this long, so a queue
# restored later still plays.
KEEP_AFTER_SECONDS = 24 * 3600

AUDIO_TYPES = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}
COVER_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
# What yt-dlp writes with restrictfilenames: no spaces, no slashes.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class TubeError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Song:
    url: str
    # File names in the cache. The cover is optional: not every site has one.
    name: str
    cover: str | None
    title: str
    artist: str
    duration: float | None


def checked(url) -> str:
    if not isinstance(url, str):
        raise TubeError("Paste a link first", 400)
    url = url.strip()
    parts = urlsplit(url)
    if (
        not url
        or len(url) > MAX_URL_LENGTH
        or parts.scheme not in ("http", "https")
        or not parts.netloc
    ):
        raise TubeError("Paste a full link, starting with https://", 400)
    return url


def download(url: str, cache: Path) -> Song:
    """Fetch the best audio of one video with yt-dlp, and its picture if the
    site has one. No ffmpeg needed: the audio is kept in the format it came in."""
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "noplaylist": True,
        "restrictfilenames": True,
        "writethumbnail": True,
        "outtmpl": {"default": str(cache / "%(extractor)s-%(id)s.%(ext)s")},
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # YouTube hides most formats behind a JavaScript challenge. Node runs it,
        # and the solver script is fetched once from GitHub and then kept.
        "js_runtimes": {"node": {}},
        "remote_components": {"ejs:github"},
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.YoutubeDLError as error:
        message = str(error).removeprefix("ERROR: ").strip()
        raise TubeError(message or "yt-dlp could not play that link") from None

    cover = next(
        (
            path.name
            for path in sorted(cache.glob(glob.escape(filename.stem) + ".*"))
            if path.suffix.lower() in COVER_TYPES
        ),
        None,
    )
    return Song(
        url=url,
        name=filename.name,
        cover=cover,
        title=info.get("title") or filename.stem,
        artist=info.get("channel") or info.get("uploader") or "",
        duration=info.get("duration"),
    )


class Tube:
    def __init__(
        self,
        cache: Path,
        history_file: Path,
        plays_file: Path | None = None,
        fetch: Callable[[str, Path], Song] = download,
    ):
        self.cache = cache
        self.history_file = history_file
        self.plays_file = plays_file or history_file.with_name("plays.json")
        self.fetch = fetch
        # One download at a time: yt-dlp is not built for parallel runs in one
        # process, and a second click on the same link then waits for the first.
        self.lock = threading.Lock()
        cache.mkdir(parents=True, exist_ok=True)

    def play(self, url) -> dict:
        """Download (or reuse) the link's audio, put it at the top of the
        history and count it. Returns the history entry."""
        url = checked(url)
        with self.lock:
            song = self.fetch(url, self.cache)
            now = time.time()
            entry = {**asdict(song), "playedAt": now}
            entries = [e for e in self._load(self.history_file) if e["url"] != url]
            entries = [entry, *entries][:HISTORY_LENGTH]
            self._save(self.history_file, entries)

            plays = self._load(self.plays_file, dict)
            counted = plays.get(url, {}).get("count", 0)
            plays[url] = {**entry, "count": counted + 1}
            self._save(self.plays_file, plays)

            self._prune(entries, self._most(plays))
            return entry

    def history(self) -> list[dict]:
        with self.lock:
            return self._load(self.history_file)

    def most_played(self) -> list[dict]:
        with self.lock:
            return self._most(self._load(self.plays_file, dict))

    def forget_history(self, url: str) -> None:
        """Take a link out of the last played list. Its audio goes with the
        usual clean-up, a day later."""
        with self.lock:
            entries = [e for e in self._load(self.history_file) if e["url"] != url]
            self._save(self.history_file, entries)

    def forget_plays(self, url: str) -> None:
        """Take a link out of the most played list, count and all."""
        with self.lock:
            plays = self._load(self.plays_file, dict)
            plays.pop(url, None)
            self._save(self.plays_file, plays)

    def file(self, name: str) -> Path | None:
        """A file in the cache by its name. The name is checked, so nothing
        outside the cache can be named."""
        if not SAFE_NAME.match(name):
            return None
        path = self.cache / name
        return path if path.is_file() else None

    @staticmethod
    def _most(plays: dict) -> list[dict]:
        ranked = sorted(plays.values(), key=lambda e: (-e["count"], -e["playedAt"]))
        return ranked[:HISTORY_LENGTH]

    @staticmethod
    def _load(path: Path, kind=list):
        try:
            data = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return kind()
        return data if isinstance(data, kind) else kind()

    @staticmethod
    def _save(path: Path, data) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2))
        temporary.replace(path)

    def _prune(self, entries: list[dict], most: list[dict]) -> None:
        """Delete the audio of songs neither in the history nor among the most
        played, once it is a day old."""
        kept = {Path(e["name"]).stem for e in [*entries, *most]}
        cutoff = time.time() - KEEP_AFTER_SECONDS
        for path in self.cache.iterdir():
            if path.is_file() and path.stem not in kept and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
