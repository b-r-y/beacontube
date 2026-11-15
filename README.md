# BeaconTube for Beacon

A Beacon external source that plays a link you paste: typically a YouTube video, but
anything [yt-dlp](https://github.com/yt-dlp/yt-dlp) supports. It shows up as its own tab in
Beacon, with a field for the link, a Play button, and the last 10 links played.

## How it works

- The audio is downloaded with yt-dlp into `data/cache`, then served from there. Beacon
  plays it like any other song, with seeking and waveforms. No ffmpeg is needed: the audio
  is kept in the format it came in (usually M4A).
- A site's picture is kept with the song as its cover, when the site has one.
- The history lives on the server, in `data/history.json`, since the page cannot keep
  anything in the browser.
- A song that drops out of the history keeps its file for a day, so a queue restored
  later still plays. After that the file is deleted.
- One download runs at a time. A second link waits for the first.

## Running it

It needs no Docker. Needs Python 3.13, [uv](https://docs.astral.sh/uv/), and
[Node.js](https://nodejs.org/). YouTube hides most of its audio behind a JavaScript
challenge, and yt-dlp runs it with Node. Without Node, many YouTube links fail with
"This video is not available", even ones that play in a browser.

```bash
TOKEN=change-me uv run main.py
```

The default port is `8802` (`PORT=...` to change it). The data folder defaults to `./data`
(`DATA_DIR=...`). Other settings:

| Variable       | Default     | What it does                                              |
| -------------- | ----------- | --------------------------------------------------------- |
| `TOKEN`        | none        | Beacon has to send it to see the page. Set one            |
| `SOURCE_NAME`  | `BeaconTube`| The name shown in the page's header                       |
| `DATA_DIR`     | `./data`    | History, cache and signing secret                         |
| `SECRET`       | made once   | Signs song addresses. Leave it unset unless you run copies |
| `HOST`, `PORT` | `0.0.0.0:8802` | Where to listen                                        |

## Connecting Beacon

In Beacon: **Settings > Library > External sources > Add source**.

| Field       | Value                                                 |
| ----------- | ----------------------------------------------------- |
| Tab name    | e.g. `Tube`                                           |
| Tab icon    | Any                                                   |
| App address | `http://localhost:8802`, as Beacon's server reaches it |
| Token       | The `TOKEN` you set                                   |

## Notes

- Sites change their pages often. When a link stops working, update yt-dlp first:
  `uv lock --upgrade-package yt-dlp && uv sync`.
- Some videos need a login or are age-restricted. This app does not pass on cookies, so
  those fail with the message yt-dlp gives.
- Keep the port internal. Anyone who has a song's address can play that song, and the
  page needs the token.
- Only download what you may. The terms of the site you take it from apply.

## Development

```bash
uv sync
uv run pytest        # no network needed: yt-dlp is replaced by a stand-in
uv run ruff format . && uv run ruff check .
```

The page is plain HTML, CSS and JavaScript in `beacontube/ui/`, no build step. The
contract with Beacon is in Beacon's help under **External source API**
([`docs/help/reference/external-source-api.md`](../../help/reference/external-source-api.md)).
