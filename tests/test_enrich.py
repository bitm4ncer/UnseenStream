from app import enrich, youtube


def test_parse_duration_variants():
    assert youtube.parse_duration("PT45S") == 45
    assert youtube.parse_duration("PT1M30S") == 90
    assert youtube.parse_duration("PT1H2M3S") == 3723
    assert youtube.parse_duration("P1DT10S") == 86410
    assert youtube.parse_duration("PT2M") == 120
    assert youtube.parse_duration(None) is None
    assert youtube.parse_duration("kaputt") is None


def test_duration_of_item():
    item = {"contentDetails": {"duration": "PT10M"}}
    assert youtube.duration_of(item) == 600
    assert youtube.duration_of({}) is None


def test_enrich_fills_missing_duration(connection, monkeypatch):
    from app import db

    conn = connection
    now = db.iso(db.utcnow())
    conn.execute(
        """
        INSERT INTO videos (id, channel_id, title, views, published_at,
                            discovered_at, last_seen, source)
        VALUES ('vid1', 'UCx', 'Titel', 0, ?, ?, ?, 'rss')
        """,
        (now, now, now),
    )
    conn.commit()

    def fake_fetch(conn, ids):
        return [
            {
                "id": ids[0],
                "contentDetails": {"duration": "PT12M"},
                "statistics": {"viewCount": "0"},
                "snippet": {"title": "Titel", "publishedAt": now},
            }
        ]

    monkeypatch.setattr(youtube, "fetch_videos", fake_fetch)

    assert enrich.enrich_batch(conn) == 1
    assert conn.execute(
        "SELECT duration_s FROM videos WHERE id = 'vid1'"
    ).fetchone()[0] == 720


def test_enrich_marks_unavailable_videos(connection, monkeypatch):
    from app import db

    conn = connection
    now = db.iso(db.utcnow())
    conn.execute(
        """
        INSERT INTO videos (id, channel_id, title, views, published_at,
                            discovered_at, last_seen, source)
        VALUES ('gone', 'UCx', 'weg', 0, ?, ?, ?, 'rss')
        """,
        (now, now, now),
    )
    conn.commit()

    monkeypatch.setattr(youtube, "fetch_videos", lambda conn, ids: [])

    enrich.enrich_batch(conn)

    assert conn.execute(
        "SELECT duration_s FROM videos WHERE id = 'gone'"
    ).fetchone()[0] == -1
