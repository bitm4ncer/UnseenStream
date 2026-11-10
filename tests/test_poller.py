from datetime import timedelta

from app import db, poller, rss

FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
  <title>Kanal</title>
  <yt:channelId>{channel_id}</yt:channelId>
  {entries}
</feed>
"""

ENTRY_TEMPLATE = """
  <entry>
    <yt:videoId>{video_id}</yt:videoId>
    <title>{title}</title>
    <published>{published}</published>
    <media:group>
      <media:thumbnail url="https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"/>
      <media:statistics views="{views}"/>
    </media:group>
  </entry>
"""


def make_entry(video_id, views=0, age_hours=1, title="Video"):
    published = db.iso(db.utcnow() - timedelta(hours=age_hours))
    return ENTRY_TEMPLATE.format(
        video_id=video_id, title=title, published=published, views=views
    )


def make_feed(channel_id, entries):
    return rss.parse_feed(
        FEED_TEMPLATE.format(channel_id=channel_id, entries="".join(entries))
    )


def insert_channel(conn, channel_id="UCtest", tier="warm", fail_streak=0):
    now = db.iso(db.utcnow())
    conn.execute(
        """
        INSERT INTO channels (id, title, first_seen, last_seen, tier, fail_streak)
        VALUES (?, 'Kanal', ?, ?, ?, ?)
        """,
        (channel_id, now, now, tier, fail_streak),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM channels WHERE id = ?", (channel_id,)
    ).fetchone()


def test_new_candidate_is_stored(connection):
    channel = insert_channel(connection, tier="cold")
    feed = make_feed("UCtest", [make_entry("vid1", views=0, age_hours=1)])

    hits = poller._apply_feed(connection, channel, feed)
    connection.commit()

    assert hits == 1
    row = connection.execute("SELECT * FROM videos WHERE id = 'vid1'").fetchone()
    assert row["views"] == 0
    assert row["source"] == "rss"

    updated = connection.execute(
        "SELECT * FROM channels WHERE id = 'UCtest'"
    ).fetchone()
    assert updated["tier"] == "warm"
    assert updated["hits"] == 1


def test_popular_video_is_ignored(connection):
    channel = insert_channel(connection)
    feed = make_feed("UCtest", [make_entry("vid2", views=250)])

    hits = poller._apply_feed(connection, channel, feed)

    assert hits == 0
    assert connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0


def test_old_video_is_ignored(connection):
    channel = insert_channel(connection)
    feed = make_feed("UCtest", [make_entry("vid3", views=0, age_hours=240)])

    hits = poller._apply_feed(connection, channel, feed)

    assert hits == 0


def test_known_video_updates_views(connection):
    channel = insert_channel(connection)
    now = db.iso(db.utcnow())
    connection.execute(
        """
        INSERT INTO videos (id, channel_id, title, views, published_at,
                            discovered_at, last_seen, source)
        VALUES ('vid4', 'UCtest', 'Video', 0, ?, ?, ?, 'rss')
        """,
        (now, now, now),
    )
    connection.commit()

    feed = make_feed("UCtest", [make_entry("vid4", views=180)])
    hits = poller._apply_feed(connection, channel, feed)
    connection.commit()

    assert hits == 0
    assert connection.execute(
        "SELECT views FROM videos WHERE id = 'vid4'"
    ).fetchone()[0] == 180


def test_failure_marks_channel_dead_after_five(connection):
    channel = insert_channel(connection, fail_streak=4)

    poller._apply_failure(connection, channel, 5)
    connection.commit()

    row = connection.execute("SELECT * FROM channels WHERE id = 'UCtest'").fetchone()
    assert row["alive"] == 0


def test_failure_keeps_channel_alive_with_backoff(connection):
    channel = insert_channel(connection, fail_streak=0)

    poller._apply_failure(connection, channel, 1)
    connection.commit()

    row = connection.execute("SELECT * FROM channels WHERE id = 'UCtest'").fetchone()
    assert row["alive"] == 1
    assert row["backoff_until"] is not None


def test_enforce_caps_demotes_excess(connection, monkeypatch):
    monkeypatch.setitem(db.config.TIERS, "hot", {"interval": 600, "cap": 1})
    for index in range(3):
        insert_channel(connection, channel_id=f"UChot{index}", tier="hot")

    poller.enforce_caps(connection)
    connection.commit()

    hot = connection.execute(
        "SELECT COUNT(*) FROM channels WHERE tier = 'hot'"
    ).fetchone()[0]
    warm = connection.execute(
        "SELECT COUNT(*) FROM channels WHERE tier = 'warm'"
    ).fetchone()[0]
    assert hot == 1
    assert warm == 2


def test_global_outage_keeps_fail_counters(connection, monkeypatch):
    for index in range(25):
        insert_channel(connection, channel_id=f"UCout{index:02d}", tier="cold")

    monkeypatch.setattr(db.config, "POLL_BATCH", {"hot": 0, "warm": 0, "cold": 100})
    monkeypatch.setattr(poller, "fetch_feed", lambda cid: (cid, "http", 404))

    stats = poller.poll_cycle(connection)

    assert stats["outage"] is True
    streaks = [row[0] for row in connection.execute("SELECT fail_streak FROM channels")]
    assert streaks and all(value == 0 for value in streaks)


def test_single_failure_increments_counter(connection, monkeypatch):
    insert_channel(connection, channel_id="UCalone", tier="cold")

    monkeypatch.setattr(db.config, "POLL_BATCH", {"hot": 0, "warm": 0, "cold": 10})
    monkeypatch.setattr(poller, "fetch_feed", lambda cid: (cid, "http", 404))

    stats = poller.poll_cycle(connection)

    assert stats["outage"] is False
    assert connection.execute(
        "SELECT fail_streak FROM channels WHERE id = 'UCalone'"
    ).fetchone()[0] == 1
