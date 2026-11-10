from datetime import datetime, timezone

from app import db


def test_schema_creates_tables(connection):
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"channels", "videos", "quota", "meta"} <= names


def test_quota_day_uses_pacific_midnight():
    # 07:00 UTC ist in Kalifornien noch der Vortag (PST, UTC-8).
    moment = datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)
    assert db.quota_day(moment) == "2026-11-09"

    later = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    assert db.quota_day(later) == "2026-11-10"


def test_spend_accumulates(connection):
    db.spend(connection, 100)
    db.spend(connection, 1)
    assert db.spent_today(connection) == 101


def test_remaining_quota_never_negative(connection, monkeypatch):
    monkeypatch.setattr(db.config, "DAILY_QUOTA", 50)
    db.spend(connection, 120)
    assert db.remaining_quota(connection) == 0


def test_meta_roundtrip(connection):
    assert db.get_meta(connection, "missing") is None
    db.set_meta(connection, "term_index", "7")
    assert db.get_meta(connection, "term_index") == "7"

def test_prune_removes_viewed_and_consumed(connection):
    now = db.utcnow()
    rows = [
        ("clean", 0, 0),
        ("viewed", 7, 0),
        ("served", 0, 1),
    ]
    for video_id, views, served in rows:
        connection.execute(
            """
            INSERT INTO videos (id, title, views, served, published_at,
                                discovered_at, last_seen, source)
            VALUES (?, 'T', ?, ?, ?, ?, ?, 'rss')
            """,
            (video_id, views, served, db.iso(now), db.iso(now), db.iso(now)),
        )
    connection.commit()

    assert db.prune_consumed(connection) == 2
    remaining = [row[0] for row in connection.execute("SELECT id FROM videos")]
    assert remaining == ["clean"]
