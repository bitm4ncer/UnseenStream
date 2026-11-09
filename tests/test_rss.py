import pytest

from app import rss


def test_parses_channel_and_entries(feed_xml):
    feed = rss.parse_feed(feed_xml)

    assert feed["channel_id"] == "UCtest"
    assert feed["channel_title"] == "Testkanal"
    assert [entry["id"] for entry in feed["entries"]] == [
        "aaaaaaaaaaa",
        "bbbbbbbbbbb",
    ]


def test_extracts_views_and_normalizes_time(feed_xml):
    feed = rss.parse_feed(feed_xml)

    first, second = feed["entries"]
    assert first["views"] == 0
    assert second["views"] == 42
    assert first["published_at"] == "2026-11-10T09:00:00Z"
    assert first["thumbnail"].endswith("mqdefault.jpg")


def test_missing_statistics_defaults_to_zero():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:yt="http://www.youtube.com/xml/schemas/2015"
          xmlns:media="http://search.yahoo.com/mrss/">
      <yt:channelId>UCx</yt:channelId>
      <entry>
        <yt:videoId>vid1</yt:videoId>
        <title>ohne Statistik</title>
        <published>2026-11-10T09:00:00+00:00</published>
      </entry>
    </feed>"""

    feed = rss.parse_feed(xml)
    assert feed["entries"][0]["views"] == 0
    assert feed["entries"][0]["thumbnail"] is None


def test_empty_feed_raises():
    with pytest.raises(rss.FeedError):
        rss.parse_feed("")


def test_broken_xml_raises():
    with pytest.raises(rss.FeedError):
        rss.parse_feed("<feed><unclosed>")


def test_garbage_raises():
    with pytest.raises(rss.FeedError):
        rss.parse_feed("<html><body>kein Feed</body></html>")
