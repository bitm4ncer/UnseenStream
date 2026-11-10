import pytest

from app import db, archive


@pytest.fixture(autouse=True)
def _no_deep_query(monkeypatch):
    """Kein Netz in Tests: alle drei Suchen standardmaessig leer."""
    monkeypatch.setattr(archive, "search_recent", lambda limit=None: [])
    monkeypatch.setattr(archive, "search_deep", lambda cursor=None, limit=None: [])
    monkeypatch.setattr(
        archive, "search_vintage", lambda year, cursor=None, limit=None: []
    )


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


class _FakeHttp:
    def __init__(self, content, status=200):
        self._content = content
        self._status = status

    def get(self, url, timeout=15):
        class Response:
            def __init__(self, content, status):
                self.content = content
                self.status_code = status

        return Response(self._content, self._status)


def test_thumb_is_placeholder_detects_generic(monkeypatch):
    monkeypatch.setattr(archive, "_http", lambda: _FakeHttp(b"x" * archive.PLACEHOLDER_BYTES))
    assert archive.thumb_is_placeholder("item") is True


def test_thumb_is_placeholder_accepts_real_frame(monkeypatch):
    monkeypatch.setattr(archive, "_http", lambda: _FakeHttp(b"x" * 9000))
    assert archive.thumb_is_placeholder("item") is False


def test_refresh_thumbnails_replaces_placeholder(connection, monkeypatch):
    connection.execute(
        """
        INSERT INTO videos (id, title, thumbnail, views, published_at,
                            discovered_at, last_seen, source, provider,
                            duration_s, media_url)
        VALUES ('thumbme', 'T', 'https://archive.org/services/img/thumbme', 0,
                '2026-11-10T00:00:00Z', '2026-11-10T00:00:00Z',
                '2026-11-10T00:00:00Z', 'archive', 'archive', 600,
                'https://archive.org/download/thumbme/v.mp4')
        """
    )
    connection.commit()

    monkeypatch.setattr(archive, "thumb_is_placeholder", lambda ident: True)
    monkeypatch.setattr(
        archive, "extract_frame", lambda url, position=3: "data:image/jpeg;base64,AAA"
    )
    monkeypatch.setattr(archive.time, "sleep", lambda seconds: None)

    assert archive.refresh_thumbnails(connection) == 1

    row = connection.execute(
        "SELECT thumbnail, thumb_checked FROM videos WHERE id = 'thumbme'"
    ).fetchone()
    assert row["thumbnail"].startswith("data:image/jpeg;base64,")
    assert row["thumb_checked"] == 1


def test_refresh_thumbnails_keeps_real_image(connection, monkeypatch):
    connection.execute(
        """
        INSERT INTO videos (id, title, thumbnail, views, published_at,
                            discovered_at, last_seen, source, provider,
                            duration_s, media_url)
        VALUES ('real', 'T', 'https://archive.org/services/img/real', 0,
                '2026-11-10T00:00:00Z', '2026-11-10T00:00:00Z',
                '2026-11-10T00:00:00Z', 'archive', 'archive', 600,
                'https://archive.org/download/real/v.mp4')
        """
    )
    connection.commit()

    monkeypatch.setattr(archive, "thumb_is_placeholder", lambda ident: False)
    monkeypatch.setattr(
        archive, "extract_frame", lambda url, position=3: (_ for _ in ()).throw(AssertionError("kein ffmpeg erwartet"))
    )

    assert archive.refresh_thumbnails(connection) == 0

    row = connection.execute(
        "SELECT thumbnail, thumb_checked FROM videos WHERE id = 'real'"
    ).fetchone()
    assert row["thumbnail"].startswith("https://archive.org/services/img/")
    assert row["thumb_checked"] == 1


def test_deep_cursor_moves_backwards(connection, monkeypatch):
    deep = [
        {**_doc("old1"), "addeddate": "2026-10-01T12:00:00Z"},
        {**_doc("old2"), "addeddate": "2026-09-20T08:00:00Z"},
    ]
    monkeypatch.setattr(
        archive, "search_deep", lambda cursor=None, limit=None: deep
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

    # Eine Sekunde vor dem aeltesten Item, damit es keinen Ueberlapp gibt.
    assert db.get_meta(connection, "archive_deep_cursor") == "2026-09-20T07:59:59Z"


def test_probe_media_accepts_video(monkeypatch):
    class Response:
        status_code = 206
        headers = {"Content-Type": "video/mp4"}

        def close(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(archive, "_http", lambda: Session())
    assert archive.probe_media("https://archive.org/download/x/v.mp4") is True


def test_probe_media_rejects_html_error_page(monkeypatch):
    class Response:
        status_code = 403
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def close(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(archive, "_http", lambda: Session())
    assert archive.probe_media("https://archive.org/download/x/v.mp4") is False


def test_vintage_year_advances_when_year_is_empty(connection):
    archive.discover(connection)

    # 2025 ist leer, also geht es beim naechsten Lauf mit 2024 weiter.
    assert db.get_meta(connection, "archive_vintage_year") == "2024"


def test_channel_title_prefers_uploader():
    assert archive._channel_title({"uploader": "someone", "collection": ["c"]}) == "someone"
    assert archive._channel_title({"collection": ["c"]}) == "c"
    assert archive._channel_title({}) == "archive.org"
