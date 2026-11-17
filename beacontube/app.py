"""The HTTP side: what Beacon asks for (/v1, /ui/, signed audio and covers)
and the page's own API under /ui/api/.

See Beacon's help page "External source API" for the contract."""

import asyncio
import hmac
from collections.abc import Iterator
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__, search
from .config import Config
from .signing import sign, verify
from .tube import AUDIO_TYPES, COVER_TYPES, Tube, TubeError

UI_DIR = Path(__file__).parent / "ui"

# A file's name never changes its content, so the browser may keep it.
_IMMUTABLE = "private, max-age=86400"


def create_app(config: Config, tube: Tube | None = None):
    tube = tube or Tube(
        config.data_dir / "cache",
        config.data_dir / "history.json",
        keep_seconds=config.keep_hours * 3600,
    )

    def item_of(entry: dict) -> dict:
        """What the page hands to Beacon for one song. Addresses relative to
        /ui/, signed: Beacon and the speakers fetch them with no header."""
        name, cover = entry["name"], entry.get("cover")
        item = {
            "audioUrl": f"../audio/{sign(config.secret, 'audio', name)}/{name}",
            "title": entry["title"],
            "artist": entry["artist"],
        }
        if cover:
            item["coverUrl"] = f"../covers/{sign(config.secret, 'cover', cover)}/{cover}"
        if entry.get("duration"):
            item["duration"] = entry["duration"]
        return item

    # --- what Beacon asks for ----------------------------------------------------

    async def health(request: Request):
        return JSONResponse({"ok": True})

    async def info(request: Request):
        return JSONResponse({"name": config.name, "version": __version__, "capabilities": []})

    async def page(request: Request):
        return FileResponse(UI_DIR / "index.html", headers={"cache-control": "no-cache"})

    async def audio(request: Request):
        name = request.path_params["name"]
        if not verify(config.secret, "audio", name, request.path_params["sig"]):
            return Response(status_code=404)
        path = tube.file(name)
        if not path or path.suffix.lower() not in AUDIO_TYPES:
            return Response(status_code=404)
        return file_response(request, path, AUDIO_TYPES[path.suffix.lower()])

    def cover_response(request: Request, name: str) -> Response:
        path = tube.file(name)
        if not path or path.suffix.lower() not in COVER_TYPES:
            return Response(status_code=404)
        return file_response(request, path, COVER_TYPES[path.suffix.lower()])

    async def cover(request: Request):
        name = request.path_params["name"]
        if not verify(config.secret, "cover", name, request.path_params["sig"]):
            return Response(status_code=404)
        return cover_response(request, name)

    # --- the page's own API ----------------------------------------------------

    async def page_cover(request: Request):
        # Under /ui/: the page shows these itself, and only /ui/ reaches it.
        return cover_response(request, request.path_params["name"])

    def page_cover_of(entry: dict) -> str | None:
        """The picture the page shows for a song: its own while the file is
        here, otherwise the video's thumbnail, which needs no download."""
        cover = entry.get("cover")
        if cover and tube.file(cover):
            return f"covers/{cover}"
        found = search.video_id(entry["url"])
        return f"thumbnails/{found}" if found else None

    def listed(entry: dict) -> dict:
        return {
            "url": entry["url"],
            "playedAt": entry["playedAt"],
            "plays": entry.get("count"),
            "cover": page_cover_of(entry),
            "item": item_of(entry),
        }

    async def history(request: Request):
        return JSONResponse([listed(entry) for entry in tube.history()])

    async def most_played(request: Request):
        return JSONResponse([listed(entry) for entry in tube.most_played()])

    async def library(request: Request):
        return JSONResponse(
            [{**listed(entry), "cached": entry["cached"]} for entry in tube.library()]
        )

    async def forget_history(request: Request):
        url = await link_in(request)
        tube.forget_history(url)
        return JSONResponse({"ok": True})

    async def forget_plays(request: Request):
        url = await link_in(request)
        tube.forget_plays(url)
        return JSONResponse({"ok": True})

    async def link_in(request: Request) -> str:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return body.get("url") if isinstance(body, dict) else ""

    async def find(request: Request):
        try:
            # yt-dlp blocks while it asks: off the event loop.
            results = await asyncio.to_thread(search.search, request.query_params.get("q"))
        except TubeError as error:
            return JSONResponse({"error": str(error)}, status_code=error.status)
        return JSONResponse(results)

    async def thumbnail(request: Request):
        data = await asyncio.to_thread(search.thumbnail, request.path_params["video_id"])
        if data is None:
            return Response(status_code=404)
        return Response(data, media_type="image/jpeg", headers={"cache-control": _IMMUTABLE})

    async def play(request: Request):
        url = await link_in(request)
        try:
            # yt-dlp blocks for as long as the download takes: off the event loop.
            entry = await asyncio.to_thread(tube.play, url)
        except TubeError as error:
            return JSONResponse({"error": str(error)}, status_code=error.status)
        return JSONResponse({"item": item_of(entry)})

    routes = [
        Route("/health", health),
        Route("/v1", info),
        Route("/ui/", page),
        Route("/ui/api/history", history),
        Route("/ui/api/most-played", most_played),
        Route("/ui/api/library", library),
        Route("/ui/api/history/remove", forget_history, methods=["POST"]),
        Route("/ui/api/most-played/remove", forget_plays, methods=["POST"]),
        Route("/ui/api/play", play, methods=["POST"]),
        Route("/ui/api/search", find),
        Route("/ui/thumbnails/{video_id}", thumbnail, methods=["GET", "HEAD"]),
        Route("/ui/covers/{name}", page_cover, methods=["GET", "HEAD"]),
        Mount("/ui", app=StaticFiles(directory=UI_DIR)),
        Route("/audio/{sig}/{name}", audio, methods=["GET", "HEAD"]),
        Route("/covers/{sig}/{name}", cover, methods=["GET", "HEAD"]),
    ]
    app = Starlette(routes=routes)
    app.state.tube = tube
    return TokenCheck(app, config.token)


def file_response(request: Request, path: Path, media_type: str) -> Response:
    """The file, with Range support: Beacon can then seek in it and draw a
    waveform. Sent with Content-Length, so it has a known end."""
    size = path.stat().st_size
    start, end = 0, size - 1
    status = 200
    headers = {
        "accept-ranges": "bytes",
        "content-type": media_type,
        "cache-control": _IMMUTABLE,
    }
    spec = request.headers.get("range", "")
    if spec.startswith("bytes="):
        first, _, last = spec[len("bytes=") :].split(",")[0].partition("-")
        unsatisfiable = Response(status_code=416, headers={"content-range": f"bytes */{size}"})
        try:
            if first:
                start = int(first)
                end = int(last) if last else size - 1
            else:
                start = max(0, size - int(last))
        except ValueError:
            return unsatisfiable
        end = min(end, size - 1)
        if start > end:
            return unsatisfiable
        status = 206
        headers["content-range"] = f"bytes {start}-{end}/{size}"
    headers["content-length"] = str(end - start + 1)
    if request.method == "HEAD":
        return Response(status_code=status, headers=headers)
    return StreamingResponse(
        _read(path, start, end - start + 1), status_code=status, headers=headers
    )


def _read(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as file:
        file.seek(start)
        while length > 0:
            chunk = file.read(min(65536, length))
            if not chunk:
                break
            length -= len(chunk)
            yield chunk


class TokenCheck:
    """With a token set, /v1 and /ui/ answer only a request that carries it
    (Beacon adds it when it passes the page through). Audio and covers stand
    on their signature instead, /health on nothing."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token:
            path = scope["path"]
            if path == "/v1" or path.startswith("/ui"):
                headers = dict(scope.get("headers") or [])
                given = headers.get(b"authorization", b"")
                if not hmac.compare_digest(given, f"Bearer {self.token}".encode()):
                    await Response("Token required", status_code=401)(scope, receive, send)
                    return
        await self.app(scope, receive, send)
