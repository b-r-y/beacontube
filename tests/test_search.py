import io

import pytest

from beacontube import search as search_module

ENTRIES = [
    {"id": "aaaaaaaaaaa", "title": "A song", "channel": "A channel", "duration": 215},
    {"id": "bbbbbbbbbbb", "title": "On air", "channel": "Radio", "live_status": "is_live"},
    {"id": "not a video", "title": "A playlist"},
    {"id": "ccccccccccc", "title": "Another", "uploader": "Someone", "duration": None},
]


class FakeYoutubeDL:
    asked = []

    def __init__(self, options):
        assert options["extract_flat"] is True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, query, download):
        assert download is False
        FakeYoutubeDL.asked.append(query)
        return {"entries": ENTRIES}


@pytest.fixture
def fake_ytdlp(monkeypatch):
    monkeypatch.setattr(FakeYoutubeDL, "asked", [])
    monkeypatch.setattr(search_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


def test_search_lists_videos_but_no_live_streams(make_client, fake_ytdlp):
    response = make_client().get("/ui/api/search", params={"q": "  some   song "})
    assert response.status_code == 200
    assert fake_ytdlp.asked == ["ytsearch12:some song"]
    assert response.json() == [
        {
            "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
            "title": "A song",
            "artist": "A channel",
            "duration": 215,
            "thumbnail": "thumbnails/aaaaaaaaaaa",
        },
        {
            "url": "https://www.youtube.com/watch?v=ccccccccccc",
            "title": "Another",
            "artist": "Someone",
            "duration": None,
            "thumbnail": "thumbnails/ccccccccccc",
        },
    ]


def test_search_needs_words(make_client, fake_ytdlp):
    client = make_client()
    assert client.get("/ui/api/search").status_code == 400
    assert client.get("/ui/api/search", params={"q": "   "}).status_code == 400
    assert fake_ytdlp.asked == []


def test_search_needs_the_token(make_client, fake_ytdlp):
    client = make_client(token="secret")
    assert client.get("/ui/api/search", params={"q": "x"}).status_code == 401
    headers = {"Authorization": "Bearer secret"}
    assert client.get("/ui/api/search", params={"q": "x"}, headers=headers).status_code == 200


def test_thumbnails_are_passed_through(make_client, monkeypatch):
    fetched = []

    def urlopen(url, timeout):
        fetched.append(url)
        return io.BytesIO(b"jpeg")

    monkeypatch.setattr(search_module.urllib.request, "urlopen", urlopen)
    client = make_client()
    picture = client.get("/ui/thumbnails/aaaaaaaaaaa")
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/jpeg"
    assert picture.content == b"jpeg"
    assert fetched == ["https://i.ytimg.com/vi/aaaaaaaaaaa/mqdefault.jpg"]

    assert client.get("/ui/thumbnails/..%2F..%2Fx").status_code == 404
    assert client.get("/ui/thumbnails/short").status_code == 404
    assert len(fetched) == 1


def test_a_missing_thumbnail_is_a_404(make_client, monkeypatch):
    def urlopen(url, timeout):
        raise OSError("not found")

    monkeypatch.setattr(search_module.urllib.request, "urlopen", urlopen)
    assert make_client().get("/ui/thumbnails/aaaaaaaaaaa").status_code == 404
