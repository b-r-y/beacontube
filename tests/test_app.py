import threading

import pytest
from conftest import fake_download

import beacontube.tube as tube_module
from beacontube.tube import Tube, TubeError


def play(client, url):
    return client.post("/ui/api/play", json={"url": url})


def audio_path(item):
    return "/" + item["audioUrl"].removeprefix("../")


def test_names_the_app(make_client):
    body = make_client().get("/v1").json()
    assert body == {"name": "BeaconTube", "version": "1.0.0", "capabilities": []}


def test_token_is_required_on_the_page_and_api(make_client):
    client = make_client(token="secret")
    assert client.get("/v1").status_code == 401
    assert client.get("/ui/").status_code == 401
    headers = {"Authorization": "Bearer secret"}
    assert client.get("/v1", headers=headers).status_code == 200
    assert client.get("/health").status_code == 200


def test_play_refuses_what_is_not_a_link(make_client):
    client = make_client()
    assert play(client, "ftp://example.com/x").status_code == 400
    assert play(client, "just some words").status_code == 400
    garbled = client.post(
        "/ui/api/play", content=b"not json", headers={"content-type": "application/json"}
    )
    assert garbled.status_code == 400


def test_play_returns_an_item_and_the_audio_plays_with_ranges(make_client):
    client = make_client()
    response = play(client, "https://www.youtube.com/watch?v=abcd")
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["title"] == "Video abcd"
    assert item["duration"] == 215
    assert item["audioUrl"].startswith("../audio/")
    assert item["coverUrl"].startswith("../covers/")

    audio = client.get(audio_path(item))
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/mp4"
    assert audio.headers["content-length"] == "1000"

    partial = client.get(audio_path(item), headers={"Range": "bytes=10-19"})
    assert partial.status_code == 206
    assert partial.headers["content-range"] == "bytes 10-19/1000"
    assert len(partial.content) == 10

    suffix = client.get(audio_path(item), headers={"Range": "bytes=-5"})
    assert suffix.status_code == 206 and len(suffix.content) == 5

    unsatisfiable = client.get(audio_path(item), headers={"Range": "bytes=5000-"})
    assert unsatisfiable.status_code == 416


def test_cover_is_served_under_its_signature(make_client):
    client = make_client()
    item = play(client, "https://www.youtube.com/watch?v=abcd").json()["item"]
    cover = item["coverUrl"].removeprefix("../")
    assert client.get("/" + cover).status_code == 200
    _, _, name = cover.split("/")
    assert client.get(f"/covers/wrong/{name}").status_code == 404


def test_audio_needs_a_valid_signature(make_client):
    client = make_client()
    item = play(client, "https://www.youtube.com/watch?v=abcd").json()["item"]
    name = audio_path(item).rsplit("/", 1)[1]
    assert client.get(f"/audio/wrong/{name}").status_code == 404
    assert client.get("/audio/wrong/../../secret").status_code == 404


def test_history_keeps_the_last_ten_newest_first(make_client):
    client = make_client()
    for n in range(12):
        play(client, f"https://www.youtube.com/watch?v=vid{n:02d}")
    history = client.get("/ui/api/history").json()
    assert len(history) == 10
    assert history[0]["url"] == "https://www.youtube.com/watch?v=vid11"
    assert history[-1]["url"] == "https://www.youtube.com/watch?v=vid02"


def test_playing_a_link_again_moves_it_to_the_top(make_client):
    client = make_client()
    play(client, "https://www.youtube.com/watch?v=aaaa")
    play(client, "https://www.youtube.com/watch?v=bbbb")
    play(client, "https://www.youtube.com/watch?v=aaaa")
    urls = [e["url"] for e in client.get("/ui/api/history").json()]
    assert urls == ["https://www.youtube.com/watch?v=aaaa", "https://www.youtube.com/watch?v=bbbb"]


def test_download_errors_reach_the_page(make_client):
    def refuse(url, cache):
        raise TubeError("Video unavailable")

    response = play(make_client(fetch=refuse), "https://www.youtube.com/watch?v=gone")
    assert response.status_code == 422
    assert response.json() == {"error": "Video unavailable"}


def test_history_carries_time_and_cover_for_the_page(make_client):
    client = make_client(token="secret")
    headers = {"Authorization": "Bearer secret"}
    client.post(
        "/ui/api/play", json={"url": "https://www.youtube.com/watch?v=abcd"}, headers=headers
    )
    entry = client.get("/ui/api/history", headers=headers).json()[0]
    assert entry["playedAt"] > 0
    assert entry["cover"].startswith("covers/")
    picture = client.get("/ui/" + entry["cover"], headers=headers)
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/webp"
    assert client.get("/ui/" + entry["cover"]).status_code == 401


def test_most_played_ranks_by_plays(make_client):
    client = make_client()
    a, b = "https://www.youtube.com/watch?v=aaaa", "https://www.youtube.com/watch?v=bbbb"
    play(client, b)
    for _ in range(3):
        play(client, a)
    play(client, b)
    top = client.get("/ui/api/most-played").json()
    assert [(e["url"], e["plays"]) for e in top] == [(a, 3), (b, 2)]
    assert top[0]["cover"].startswith("covers/")
    assert top[0]["item"]["audioUrl"].startswith("../audio/")


def test_removing_from_last_played_keeps_the_count(make_client):
    client = make_client()
    a, b = "https://www.youtube.com/watch?v=aaaa", "https://www.youtube.com/watch?v=bbbb"
    play(client, a)
    play(client, b)
    client.post("/ui/api/history/remove", json={"url": a})
    assert [e["url"] for e in client.get("/ui/api/history").json()] == [b]
    assert [e["url"] for e in client.get("/ui/api/most-played").json()] == [b, a]


def test_removing_from_most_played_keeps_the_history(make_client):
    client = make_client()
    a, b = "https://www.youtube.com/watch?v=aaaa", "https://www.youtube.com/watch?v=bbbb"
    play(client, a)
    play(client, b)
    client.post("/ui/api/most-played/remove", json={"url": a})
    assert [e["url"] for e in client.get("/ui/api/most-played").json()] == [b]
    assert [e["url"] for e in client.get("/ui/api/history").json()] == [b, a]


def test_removing_an_unknown_link_is_harmless(make_client):
    client = make_client()
    assert client.post("/ui/api/history/remove", json={"url": "nope"}).json() == {"ok": True}
    assert client.post("/ui/api/most-played/remove", json={}).json() == {"ok": True}


def test_the_lists_answer_while_a_download_runs(tmp_path):
    started, finish = threading.Event(), threading.Event()

    def slow_download(url, cache):
        started.set()
        finish.wait(5)
        return fake_download(url, cache)

    tube = Tube(tmp_path / "cache", tmp_path / "history.json", fetch=slow_download)
    playing = threading.Thread(target=tube.play, args=("https://www.youtube.com/watch?v=slow",))
    playing.start()
    assert started.wait(5)

    answers = []
    reader = threading.Thread(target=lambda: answers.append((tube.history(), tube.most_played())))
    reader.start()
    reader.join(1)
    finish.set()
    playing.join(5)
    assert answers == [([], [])]
    assert tube.history()[0]["url"] == "https://www.youtube.com/watch?v=slow"


class FakeYoutubeDL:
    """Stands in for yt_dlp.YoutubeDL in download(): returns the given info."""

    info: dict = {}
    downloaded = False

    def __init__(self, options):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        assert download is False
        return dict(self.info)

    def process_ie_result(self, info, download):
        FakeYoutubeDL.downloaded = True
        return info

    def prepare_filename(self, info):
        return f"/nowhere/{info['id']}.m4a"


@pytest.mark.parametrize("live", [{"is_live": True}, {"live_status": "is_upcoming"}])
def test_live_streams_are_refused_before_downloading(monkeypatch, tmp_path, live):
    monkeypatch.setattr(FakeYoutubeDL, "info", {"id": "x", "title": "Live", **live})
    monkeypatch.setattr(FakeYoutubeDL, "downloaded", False)
    monkeypatch.setattr(tube_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    with pytest.raises(TubeError, match="Live streams"):
        tube_module.download("https://www.youtube.com/watch?v=live", tmp_path)
    assert FakeYoutubeDL.downloaded is False


def test_videos_are_downloaded(monkeypatch, tmp_path):
    info = {"id": "x", "title": "A video", "live_status": "was_live", "duration": 60}
    monkeypatch.setattr(FakeYoutubeDL, "info", info)
    monkeypatch.setattr(FakeYoutubeDL, "downloaded", False)
    monkeypatch.setattr(tube_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    song = tube_module.download("https://www.youtube.com/watch?v=x", tmp_path)
    assert FakeYoutubeDL.downloaded is True
    assert (song.name, song.title, song.duration) == ("x.m4a", "A video", 60)
