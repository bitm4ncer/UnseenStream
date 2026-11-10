from app import archive


def _doc(identifier="item1", downloads=0, title="Titel"):
    return {
        "identifier": identifier,
        "title": title,
        "addeddate": "2026-11-10T00:00:00Z",
        "downloads": downloads,
        "collection": ["opensource_movies"],
    }


def test_discover_inserts_archive_item(connection, monkeypatch):
    monkeypatch.setattr(archive, "search_recent", lambda limit=None: [_doc()])
    monkeypatch.setattr(
        archive,
        "fetch_metadata",
        lambda ident: {
            "duration_s": 600,
            "size": 1,
            "media_url": f"https://archive.org/download/{ident}/video.mp4",
        },
    )
    monkeypatch.setattr(archive.time, "sleep", lambda seconds: None)

    stats = archive.discover(connection)

    assert stats["added"] == 1
    row = connection.execute("SELECT * FROM videos WHERE id = 'item1'").fetchone()
    assert row["provider"] == "archive"
    assert row["duration_s"] == 600
    assert row["views"] == 0
    assert row["source"] == "archive"
    assert row["media_url"].endswith("/video.mp4")


def test_discover_skips_items_without_video(connection, monkeypatch):
    monkeypatch.setattr(archive, "search_recent", lambda limit=None: [_doc("novideo")])
    monkeypatch.setattr(archive, "fetch_metadata", lambda ident: None)
    monkeypatch.setattr(archive.time, "sleep", lambda seconds: None)

    stats = archive.discover(connection)

    assert stats["added"] == 0
    assert connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0


def test_discover_refreshes_known_items(connection, monkeypatch):
    connection.execute(
        """
        INSERT INTO videos (id, title, views, published_at, discovered_at,
                            last_seen, source, provider, duration_s, media_url)
        VALUES ('known', 'T', 0, '2026-11-10T00:00:00Z', '2026-11-10T00:00:00Z',
                '2026-11-10T00:00:00Z', 'archive', 'archive', 600,
                'https://archive.org/download/known/v.mp4')
        """
    )
    connection.commit()

    monkeypatch.setattr(
        archive, "search_recent", lambda limit=None: [_doc("known", downloads=5)]
    )
    monkeypatch.setattr(
        archive, "fetch_metadata", lambda ident: (_ for _ in ()).throw(AssertionError("kein Metadata-Call erwartet"))
    )

    stats = archive.discover(connection)

    assert stats["refreshed"] == 1
    assert connection.execute(
        "SELECT views FROM videos WHERE id = 'known'"
    ).fetchone()[0] == 5


def test_discover_backfills_media_url(connection, monkeypatch):
    connection.execute(
        """
        INSERT INTO videos (id, title, views, published_at, discovered_at,
                            last_seen, source, provider, duration_s)
        VALUES ('old', 'T', 0, '2026-11-10T00:00:00Z', '2026-11-10T00:00:00Z',
                '2026-11-10T00:00:00Z', 'archive', 'archive', 600)
        """
    )
    connection.commit()

    monkeypatch.setattr(
        archive, "search_recent", lambda limit=None: [_doc("old")]
    )
    monkeypatch.setattr(
        archive,
        "fetch_metadata",
        lambda ident: {
            "duration_s": 600,
            "size": 1,
            "media_url": f"https://archive.org/download/{ident}/v.mp4",
        },
    )
    monkeypatch.setattr(archive.time, "sleep", lambda seconds: None)

    archive.discover(connection)

    row = connection.execute("SELECT media_url FROM videos WHERE id = 'old'").fetchone()
    assert row["media_url"].endswith("/v.mp4")


def test_channel_title_prefers_uploader():
    assert archive._channel_title({"uploader": "someone", "collection": ["c"]}) == "someone"
    assert archive._channel_title({"collection": ["c"]}) == "c"
    assert archive._channel_title({}) == "archive.org"
