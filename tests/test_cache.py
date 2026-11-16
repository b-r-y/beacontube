import os
import time

import pytest
from conftest import fake_download

from beacontube.config import load
from beacontube.tube import HISTORY_LENGTH, KEEP_AFTER_SECONDS, Tube

OLD = "https://www.youtube.com/watch?v=old0"


def play(client, url):
    return client.post("/ui/api/play", json={"url": url})


def cached(client, url):
    """The song's files in the cache, by its history or most played entry."""
    tube = client.app.app.state.tube
    entry = next(e for e in [*tube.history(), *tube.most_played()] if e["url"] == url)
    return sorted(tube.cache.glob(os.path.splitext(entry["name"])[0] + ".*"))


def age(paths, seconds):
    then = time.time() - seconds
    for path in paths:
        os.utime(path, (then, then))


def push_out(client):
    """Plays enough other links, each twice, that one played once leaves both lists."""
    for n in range(HISTORY_LENGTH):
        for _ in range(2):
            play(client, f"https://www.youtube.com/watch?v=other{n:02d}")


def test_a_song_keeps_its_files_for_a_day_after_leaving_the_lists(make_client):
    client = make_client()
    play(client, OLD)
    files = cached(client, OLD)
    # Downloaded three days ago, and listed all that time.
    age(files, 3 * 86400)
    push_out(client)
    assert files and all(path.exists() for path in files)


def test_a_song_out_of_the_lists_for_over_a_day_is_deleted(make_client):
    client = make_client()
    play(client, OLD)
    files = cached(client, OLD)
    push_out(client)
    age(files, KEEP_AFTER_SECONDS + 60)
    play(client, "https://www.youtube.com/watch?v=next")
    assert files and not any(path.exists() for path in files)


def test_a_removed_song_keeps_its_files_for_a_day(make_client):
    client = make_client()
    play(client, OLD)
    files = cached(client, OLD)
    age(files, 3 * 86400)
    client.post("/ui/api/history/remove", json={"url": OLD})
    client.post("/ui/api/most-played/remove", json={"url": OLD})
    play(client, "https://www.youtube.com/watch?v=next")
    assert files and all(path.exists() for path in files)


def test_keep_hours_sets_how_long_files_stay(tmp_path):
    tube = Tube(
        tmp_path / "cache", tmp_path / "history.json", fetch=fake_download, keep_seconds=48 * 3600
    )
    tube.play(OLD)
    files = sorted((tmp_path / "cache").iterdir())
    for n in range(HISTORY_LENGTH):
        for _ in range(2):
            tube.play(f"https://www.youtube.com/watch?v=other{n:02d}")
    age(files, 30 * 3600)
    tube.play("https://www.youtube.com/watch?v=next")
    assert all(path.exists() for path in files)
    age(files, 50 * 3600)
    tube.play("https://www.youtube.com/watch?v=last")
    assert not any(path.exists() for path in files)


def test_keep_hours_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("KEEP_HOURS", raising=False)
    assert load().keep_hours == 24
    monkeypatch.setenv("KEEP_HOURS", "168")
    assert load().keep_hours == 168


def test_keep_hours_is_at_least_a_day(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KEEP_HOURS", "2")
    assert load().keep_hours == 24
    assert "less than a day" in caplog.text


def test_keep_hours_has_to_be_a_number(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KEEP_HOURS", "a week")
    with pytest.raises(SystemExit, match="KEEP_HOURS"):
        load()
