"""Discoverer: findet neue Channels ueber die YouTube-Suche."""

import logging
import random
import time
from datetime import timedelta

from . import config, db, youtube

logger = logging.getLogger(__name__)


def load_terms(path: str | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    try:
        with open(path or config.SEARCH_TERMS_FILE, "r", encoding="utf-8") as handle:
            for line in handle:
                term = line.strip()
                if not term or term.startswith("#"):
                    continue
                if term not in seen:
                    seen.add(term)
                    terms.append(term)
    except FileNotFoundError:
        logger.warning("Suchbegriffe nicht gefunden, nutze Fallback")
        return ["MOV", "DSC", "IMG", "VID", "video", "clip"]

    random.SystemRandom().shuffle(terms)
    return terms


def next_term(conn, terms: list[str]) -> str:
    index = int(db.get_meta(conn, "term_index", "0") or 0)
    term = terms[index % len(terms)]
    db.set_meta(conn, "term_index", str((index + 1) % len(terms)))
    return term


def _upsert_video(conn, item: dict, source: str) -> None:
    snippet = item.get("snippet", {})
    now = db.iso(db.utcnow())
    conn.execute(
        """
        INSERT INTO videos
            (id, channel_id, channel_title, title, thumbnail, views,
             published_at, discovered_at, last_seen, source, duration_s)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            views = excluded.views,
            title = excluded.title,
            thumbnail = excluded.thumbnail,
            last_seen = excluded.last_seen,
            duration_s = COALESCE(excluded.duration_s, videos.duration_s)
        """,
        (
            item["id"],
            snippet.get("channelId"),
            snippet.get("channelTitle"),
            snippet.get("title"),
            snippet.get("thumbnails", {}).get("medium", {}).get("url"),
            youtube.view_count(item),
            db.normalize_ts(snippet["publishedAt"])
            if snippet.get("publishedAt")
            else None,
            now,
            now,
            source,
            youtube.duration_of(item),
        ),
    )


def _upsert_channel(conn, channel_id: str, title: str | None, tier: str) -> None:
    now = db.iso(db.utcnow())
    conn.execute(
        """
        INSERT INTO channels (id, title, first_seen, last_seen, tier)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = COALESCE(excluded.title, channels.title),
            last_seen = excluded.last_seen
        """,
        (channel_id, title, now, now, tier),
    )


def discover_once(conn, dry_run: bool = False) -> dict:
    """Ein Suchlauf. Rueckgabe: Statistik fuer Logging/Tests."""
    if db.remaining_quota(conn) < config.SEARCH_COST:
        logger.info("Tagesquota erschoepft, Discoverer pausiert")
        return {"status": "quota_exhausted"}

    terms = load_terms()
    term = next_term(conn, terms)
    published_after = db.iso(db.utcnow() - timedelta(hours=config.SEARCH_WINDOW_HOURS))

    logger.info("Suche nach %r (ab %s)", term, published_after)
    try:
        hits = youtube.search_videos(conn, term, published_after)
    except youtube.QuotaExceeded:
        logger.warning("YouTube meldet quotaExceeded - Pause bis Reset")
        return {"status": "quota_exceeded"}
    except youtube.ApiError as exc:
        logger.error("Suche fehlgeschlagen: %s", exc)
        return {"status": "error", "error": str(exc)}

    if dry_run:
        logger.info("[dry-run] %d Treffer, keine Schreibvorgaenge", len(hits))
        return {"status": "dry_run", "found": len(hits)}

    known = {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM videos ORDER BY discovered_at DESC LIMIT 200000"
        )
    }
    new_ids = [item["id"]["videoId"] for item in hits if item["id"]["videoId"] not in known]

    added_videos = 0
    added_channels = 0
    for start in range(0, len(new_ids), config.BATCH_SIZE):
        batch = new_ids[start : start + config.BATCH_SIZE]
        try:
            details = youtube.fetch_videos(conn, batch)
        except youtube.QuotaExceeded:
            logger.warning("Quota waehrend Anreicherung erschoepft")
            break
        except youtube.ApiError as exc:
            logger.error("Anreicherung fehlgeschlagen: %s", exc)
            break

        for item in details:
            views = youtube.view_count(item)
            if views > config.MAX_VIEWS:
                continue
            _upsert_video(conn, item, source="search")
            channel_id = item.get("snippet", {}).get("channelId")
            if channel_id:
                _upsert_channel(
                    conn, channel_id, item["snippet"].get("channelTitle"), "warm"
                )
                added_channels += 1
            added_videos += 1

    conn.commit()
    db.set_meta(conn, "last_discovery", db.iso(db.utcnow()))

    stats = {
        "status": "ok",
        "term": term,
        "found": len(hits),
        "new_videos": added_videos,
        "new_channels": added_channels,
        "quota_left": db.remaining_quota(conn),
    }
    logger.info(
        "Lauf fertig: %(new_videos)s Videos, %(new_channels)s Channels, "
        "%(quota_left)s Units uebrig" % stats
    )
    return stats


def run(dry_run: bool = False, once: bool = False) -> None:
    conn = db.connect()
    interval = max(60, int(3600 / max(1, config.SEARCHES_PER_HOUR)))

    while True:
        result = discover_once(conn, dry_run=dry_run)
        if once:
            return
        if result.get("status") == "quota_exhausted":
            # Bis zum naechsten Quota-Tag warten.
            time.sleep(900)
            continue
        if result.get("status") in {"quota_exceeded", "error"}:
            time.sleep(min(3600, interval * 4))
            continue
        time.sleep(interval)
