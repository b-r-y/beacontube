from beacontube.tube import HISTORY_LENGTH


def play(client, url):
    return client.post("/ui/api/play", json={"url": url})


def test_the_library_lists_every_link_ever_played(make_client):
    client = make_client()
    for n in range(HISTORY_LENGTH + 5):
        play(client, f"https://www.youtube.com/watch?v=video{n:06d}")
    play(client, "https://www.youtube.com/watch?v=video000003")
    library = client.get("/ui/api/library").json()
    assert len(library) == HISTORY_LENGTH + 5
    assert library[0]["url"] == "https://www.youtube.com/watch?v=video000003"
    assert library[0]["plays"] == 2
    assert all(entry["cached"] for entry in library)


def test_a_song_whose_files_are_gone_shows_its_thumbnail(make_client):
    client = make_client()
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    play(client, url)
    tube = client.app.app.state.tube
    for path in tube.cache.iterdir():
        path.unlink()
    entry = client.get("/ui/api/library").json()[0]
    assert entry["cached"] is False
    assert entry["cover"] == "thumbnails/abcdefghijk"


def test_removing_from_most_played_takes_it_out_of_the_library(make_client):
    client = make_client()
    a, b = (
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    )
    play(client, a)
    play(client, b)
    client.post("/ui/api/most-played/remove", json={"url": a})
    assert [e["url"] for e in client.get("/ui/api/library").json()] == [b]


def test_the_library_needs_the_token(make_client):
    client = make_client(token="secret")
    assert client.get("/ui/api/library").status_code == 401
