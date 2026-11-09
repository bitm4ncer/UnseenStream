"""Einmalige Migration: alter Pool -> Channel-Watchlist."""

import json
import logging

from . import config, db, youtube

logger = logging.getLogger(__name__)


def _load_ids(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    videos = data.get("videos", []) if isinstance(data, dict) else data
    ids = []
    for entry in videos:
        video_id = entry.get("id") if isinstance(entry, dict) else None
        if video_id:
            ids.append(video_id)
    return ids


def run(pool_file: str, limit: int = 5000, dry_run: bool = False) -> dict:
    ids = _load_ids(pool_file)[:limit]
    if dry_run:
        logger.info("[dry-run] %d Video-IDs wuerden aufgeloest", len(ids))
        return {"status": "dry_run", "ids": len(ids)}

    conn = db.connect()
    channels: set[str] = set()
    now = db.iso(db.utcnow())

    for start in range(0, len(ids), config.BATCH_SIZE):
        if db.remaining_quota(conn) < config.VIDEOS_COST:
            logger.warning("Quota erschoepft, Seed bricht ab")
            break

        batch = ids[start : start + config.BATCH_SIZE]
        try:
            items = youtube.fetch_videos(conn, batch)
        except youtube.ApiError as exc:
            logger.error("Batch fehlgeschlagen: %s", exc)
            break

        for item in items:
            snippet = item.get("snippet", {})
            channel_id = snippet.get("channelId")
            if not channel_id or channel_id in channels:
                continue
            channels.add(channel_id)
            conn.execute(
                """
                INSERT INTO channels (id, title, first_seen, last_seen, tier)
                VALUES (?, ?, ?, ?, 'cold')
                ON CONFLICT(id) DO NOTHING
                """,
                (channel_id, snippet.get("channelTitle"), now, now),
            )

        conn.commit()
        logger.info(
            "%d/%d IDs aufgeloest, %d Channels", min(start + 50, len(ids)), len(ids), len(channels)
        )

    stats = {
        "status": "ok",
        "ids": len(ids),
        "channels": len(channels),
        "quota_left": db.remaining_quota(conn),
    }
    logger.info("Seed fertig: %(channels)s Channels, %(quota_left)s Units uebrig" % stats)
    return stats
