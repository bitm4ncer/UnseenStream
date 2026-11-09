import pytest

from app import db


@pytest.fixture
def connection(tmp_path, monkeypatch):
    """Frische SQLite-Datei pro Test, ohne den echten Datenpfad anzufassen."""
    monkeypatch.setattr(db.config, "DB_PATH", str(tmp_path / "test.db"))
    db._local.__dict__.clear()
    conn = db.connect()
    yield conn
    conn.close()
    db._local.__dict__.clear()


@pytest.fixture
def feed_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
  <link rel="self" href="https://www.youtube.com/feeds/videos.xml?channel_id=UCtest"/>
  <title>Testkanal</title>
  <yt:channelId>UCtest</yt:channelId>
  <entry>
    <id>yt:video:aaaaaaaaaaa</id>
    <yt:videoId>aaaaaaaaaaa</yt:videoId>
    <title>Erstes Video</title>
    <published>2026-11-10T09:00:00+00:00</published>
    <media:group>
      <media:title>Erstes Video</media:title>
      <media:thumbnail url="https://i.ytimg.com/vi/aaaaaaaaaaa/mqdefault.jpg" width="320" height="180"/>
      <media:statistics views="0"/>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:bbbbbbbbbbb</id>
    <yt:videoId>bbbbbbbbbbb</yt:videoId>
    <title>Zweites Video</title>
    <published>2026-11-10T08:30:00+00:00</published>
    <media:group>
      <media:thumbnail url="https://i.ytimg.com/vi/bbbbbbbbbbb/mqdefault.jpg"/>
      <media:statistics views="42"/>
    </media:group>
  </entry>
</feed>
"""
