import hashlib
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from beacontube.app import create_app
from beacontube.config import Config
from beacontube.tube import Song, Tube


def fake_download(url: str, cache: Path) -> Song:
    """Stands in for yt-dlp: writes a short audio file and a picture, no network."""
    stem = "fake-" + hashlib.sha256(url.encode()).hexdigest()[:10]
    (cache / f"{stem}.m4a").write_bytes(b"0123456789" * 100)
    (cache / f"{stem}.webp").write_bytes(b"picture")
    return Song(
        url=url,
        name=f"{stem}.m4a",
        cover=f"{stem}.webp",
        title=f"Video {url[-4:]}",
        artist="A channel",
        duration=215,
    )


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        data_dir=tmp_path,
        name="BeaconTube",
        token="",
        secret=b"test-secret",
        host="127.0.0.1",
        port=8802,
    )


@pytest.fixture
def make_client(config: Config, tmp_path: Path):
    def make(token: str = "", fetch=fake_download) -> TestClient:
        cfg = Config(**{**config.__dict__, "token": token})
        tube = Tube(tmp_path / "cache", tmp_path / "history.json", fetch=fetch)
        return TestClient(create_app(cfg, tube))

    return make
