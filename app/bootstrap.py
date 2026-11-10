"""Fallback ohne RSS: fuellt den Pool ueber die Uploads-Playlists der API.

Costet 2 Units pro Channel (1 playlistItems + 1 videos.list) und ist damit
nur fuer eine begrenzte Auswahl gedacht - als Ueberbrueckung, solange
YouTubes RSS-Endpoint unzuverlaessig ist.
"""

import logging

from . import config, db, poller, youtube

logger = logging.getLogger(__name__)


def _entries(items: list[dict]) -> list[dict]:
    entries = []
    for item in items:
        snippet = item.get("snippet", {})
        published = snippet.get("publishedAt")
        entries.append(
            {
                "id": item["id"],
                "title": snippet.get("title"),
                "published_at": db.normalize_ts(published),
                "thumbnail": snippet.get("thumbnails", {})
                .get("medium", {})
                .get("url"),
                "views": youtube.view_count(item),
                "duration_s": youtube.duration_of(item),
            }
        )
    return entries


def run(limit: int = 500, dry_run: bool = False) -> dict:
    conn = db.connect()
    channels = conn.execute(
        """
        SELECT * FROM channels
        WHERE alive = 1 AND last_poll IS NULL
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if dry_run:
        logger.info("[dry-run] %d Channels wuerden ueber die API geprueft", len(channels))
        return {"status": "dry_run", "channels": len(channels)}

    checked = 0
    hits = 0
    for channel in channels:
        if db.remaining_quota(conn) < 10:
            logger.warning("Quota knapp, Bootstrap bricht ab")
            break

        try:
            items = youtube.playlist_items(
                conn, youtube.uploads_playlist(channel["id"])
            )
        except youtube.QuotaExceeded:
            logger.warning("Quota erschoepft")
            break
        except youtube.ApiError as exc:
            logger.debug("Playlist %s: %s", channel["id"], exc)
            continue

        video_ids = [
            item["snippet"]["resourceId"]["videoId"]
            for item in items
            if item.get("snippet", {}).get("resourceId", {}).get("videoId")
        ]
        if not video_ids:
            continue

        try:
            details = youtube.fetch_videos(conn, video_ids)
        except youtube.ApiError as exc:
            logger.debug("Details %s: %s", channel["id"], exc)
            continue

        feed = {
            "channel_id": channel["id"],
            "channel_title": details[0]["snippet"].get("channelTitle")
            if details
            else channel["title"],
            "entries": _entries(details),
        }
        hits += poller._apply_feed(conn, channel, feed)
        checked += 1

        if checked % 50 == 0:
            conn.commit()
            logger.info(
                "%d Channels geprueft, %d Kandidaten, %d Units uebrig",
                checked,
                hits,
                db.remaining_quota(conn),
            )

    conn.commit()
    stats = {
        "status": "ok",
        "channels": checked,
        "candidates": hits,
        "quota_left": db.remaining_quota(conn),
    }
    logger.info(
        "Bootstrap fertig: %(channels)s Channels, %(candidates)s Kandidaten, "
        "%(quota_left)s Units uebrig" % stats
    )
    return stats
