"""Parser fuer YouTubes oeffentliche Channel-Feeds."""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


class FeedError(ValueError):
    """Feed konnte nicht gelesen werden."""


def _normalize_ts(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _views(group: ET.Element | None) -> int:
    if group is None:
        return 0
    stats = group.find("media:statistics", NS)
    if stats is None:
        return 0
    raw = stats.get("views")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _thumbnail(entry: ET.Element, group: ET.Element | None) -> str | None:
    for parent in (group, entry):
        if parent is None:
            continue
        thumb = parent.find("media:thumbnail", NS)
        if thumb is not None and thumb.get("url"):
            return thumb.get("url")
    return None


def parse_feed(xml_text: str) -> dict:
    """Liest Channel-ID, Titel und Eintraege eines Feeds.

    Rueckgabe: {"channel_id", "channel_title", "entries": [...]}
    Jeder Eintrag: id, title, published_at, thumbnail, views.
    """
    if not xml_text or not xml_text.strip():
        raise FeedError("leerer Feed")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FeedError(f"XML nicht lesbar: {exc}") from exc

    channel_id = root.findtext("yt:channelId", namespaces=NS)
    channel_title = root.findtext("a:title", namespaces=NS)

    entries = []
    for node in root.findall("a:entry", NS):
        video_id = node.findtext("yt:videoId", namespaces=NS)
        if not video_id:
            continue

        group = node.find("media:group", NS)
        entries.append(
            {
                "id": video_id,
                "title": (node.findtext("a:title", namespaces=NS) or "").strip(),
                "published_at": _normalize_ts(
                    node.findtext("a:published", namespaces=NS)
                ),
                "thumbnail": _thumbnail(node, group),
                "views": _views(group),
            }
        )

    if channel_id is None and not entries:
        raise FeedError("weder Channel-ID noch Eintraege gefunden")

    return {
        "channel_id": channel_id,
        "channel_title": channel_title,
        "entries": entries,
    }
