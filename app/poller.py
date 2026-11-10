"""Poller: haelt die Watchlist ueber die oeffentlichen RSS-Feeds aktuell."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests

from . import config, db, rss, tiers

logger = logging.getLogger(__name__)

_thread_local = threading.local()
_rate_lock = threading.Lock()
_last_request_at = [0.0]


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = config.USER_AGENT
        _thread_local.session = session
    return session


def _throttle() -> None:
    """Globales Rate-Limit: hoechstens POLL_RATE Requests pro Sekunde."""
    with _rate_lock:
        now = time.monotonic()
        earliest = _last_request_at[0] + (1.0 / max(0.1, config.POLL_RATE))
        if earliest > now:
            time.sleep(earliest - now)
        _last_request_at[0] = time.monotonic()


def fetch_feed(channel_id: str) -> tuple[str, str, object]:
    """Holt einen Feed mit einem Wiederholungsversuch.

    YouTube antwortet seit Ende Oktober 2026 sporadisch mit 404/500 auf
    gueltige Feeds. Ein einzelner Fehlschlag sagt daher nichts aus.
    """
    url = config.FEED_URL.format(channel_id=channel_id)
    last: tuple[str, str, object] = (channel_id, "error", "kein Versuch")

    for attempt in range(2):
        _throttle()
        try:
            response = _session().get(url, timeout=config.FEED_TIMEOUT)
        except requests.RequestException as exc:
            last = (channel_id, "error", str(exc))
        else:
            if response.status_code == 200:
                return channel_id, "ok", response.text
            last = (channel_id, "http", response.status_code)
            if response.status_code not in (404, 429, 500, 502, 503, 504):
                return last

        time.sleep(0.4 * (attempt + 1))

    return last


def _age_ok(published_at: str | None) -> bool:
    if config.MAX_AGE_HOURS <= 0:
        return True
    if not published_at:
        return False
    cutoff = db.utcnow() - timedelta(hours=config.MAX_AGE_HOURS)
    return db.parse_iso(published_at) >= cutoff


def _apply_feed(conn, channel, feed: dict) -> int:
    """Schreibt Feed-Eintraege in die DB. Rueckgabe: Anzahl neuer Kandidaten."""
    now = db.iso(db.utcnow())
    channel_id = channel["id"]
    channel_title = feed.get("channel_title") or channel["title"]

    existing = {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM videos WHERE channel_id = ?", (channel_id,)
        )
    }

    new_hits = 0
    for entry in feed["entries"]:
        video_id = entry["id"]
        views = entry["views"]

        if video_id in existing:
            conn.execute(
                "UPDATE videos SET views = ?, last_seen = ? WHERE id = ?",
                (views, now, video_id),
            )
            continue

        if views > config.MAX_VIEWS or not _age_ok(entry["published_at"]):
            continue

        conn.execute(
            """
            INSERT INTO videos
                (id, channel_id, channel_title, title, thumbnail, views,
                 published_at, discovered_at, last_seen, source, duration_s)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'rss', ?)
            ON CONFLICT(id) DO UPDATE SET
                duration_s = COALESCE(excluded.duration_s, videos.duration_s)
            """,
            (
                video_id,
                channel_id,
                channel_title,
                entry["title"],
                entry["thumbnail"],
                views,
                entry["published_at"],
                now,
                now,
                entry.get("duration_s"),
            ),
        )
        existing.add(video_id)
        new_hits += 1

    tier, hit_streak, polls_since_hit = tiers.apply_poll_result(
        channel["tier"],
        new_hits,
        channel["hit_streak"],
        channel["polls_since_hit"],
    )

    conn.execute(
        """
        UPDATE channels SET
            title = COALESCE(?, title),
            last_poll = ?, last_seen = ?,
            tier = ?, polls = polls + 1,
            hits = hits + ?, hit_streak = ?, polls_since_hit = ?,
            fail_streak = 0, backoff_until = NULL
        WHERE id = ?
        """,
        (
            channel_title,
            now,
            now,
            tier,
            new_hits,
            hit_streak,
            polls_since_hit,
            channel_id,
        ),
    )
    return new_hits


def _apply_failure(conn, channel, fail_streak: int) -> None:
    now = db.utcnow()
    alive = 0 if tiers.is_dead(fail_streak) else 1
    backoff = None
    if not tiers.is_dead(fail_streak):
        backoff = db.iso(now + timedelta(seconds=tiers.backoff_seconds(fail_streak)))

    conn.execute(
        """
        UPDATE channels SET
            last_poll = ?, fail_streak = ?, alive = ?, backoff_until = ?
        WHERE id = ?
        """,
        (db.iso(now), fail_streak, alive, backoff, channel["id"]),
    )
    if not alive:
        logger.info("Channel %s deaktiviert (mehrfach nicht erreichbar)", channel["id"])


def enforce_caps(conn) -> None:
    """Haelt die Tier-Groessen ein und loescht den Cold-Ueberhang."""
    for tier_name in config.TIER_ORDER:
        cap = config.TIERS[tier_name]["cap"]
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM channels WHERE alive = 1 AND tier = ?",
            (tier_name,),
        ).fetchone()

        excess = count - cap
        if excess <= 0:
            continue

        rows = conn.execute(
            """
            SELECT id FROM channels
            WHERE alive = 1 AND tier = ?
            ORDER BY hits ASC, COALESCE(last_seen, '') ASC
            LIMIT ?
            """,
            (tier_name, excess),
        ).fetchall()

        target = tiers.next_tier_on_cap(tier_name)
        ids = [row["id"] for row in rows]
        if not ids:
            continue

        if target is None:
            conn.executemany("DELETE FROM channels WHERE id = ?", [(i,) for i in ids])
            logger.info("%d Channels aus %s geloescht", len(ids), tier_name)
        else:
            conn.executemany(
                "UPDATE channels SET tier = ? WHERE id = ?",
                [(target, i) for i in ids],
            )
            logger.debug("%d Channels von %s nach %s", len(ids), tier_name, target)


def _due_channels(conn, tier_name: str) -> list:
    now = db.utcnow()
    cutoff = db.iso(now - timedelta(seconds=config.TIERS[tier_name]["interval"]))
    return conn.execute(
        """
        SELECT id, title, tier, hit_streak, polls_since_hit, fail_streak
        FROM channels
        WHERE alive = 1 AND tier = ?
          AND (last_poll IS NULL OR last_poll <= ?)
          AND (backoff_until IS NULL OR backoff_until <= ?)
        ORDER BY COALESCE(last_poll, '') ASC
        LIMIT ?
        """,
        (tier_name, cutoff, db.iso(now), config.POLL_BATCH[tier_name]),
    ).fetchall()


def poll_cycle(conn, dry_run: bool = False) -> dict:
    due: list = []
    for tier_name in config.TIER_ORDER:
        due.extend(_due_channels(conn, tier_name))

    if not due:
        return {"polled": 0, "new_videos": 0, "failed": 0}

    if dry_run:
        logger.info("[dry-run] %d Channels faellig", len(due))
        return {"status": "dry_run", "polled": 0, "due": len(due)}

    results = []
    with ThreadPoolExecutor(max_workers=config.POLL_WORKERS) as pool:
        results = list(pool.map(fetch_feed, [row["id"] for row in due]))

    by_id = {row["id"]: row for row in due}
    new_videos = 0
    failed = 0

    # Globaler Ausfall? Dann keine Fehlzaehler erhoehen, sonst raeumt ein
    # YouTube-Ausfall die ganze Watchlist ab.
    outage = len(results) >= 20 and (
        sum(1 for _, kind, _ in results if kind != "ok") / len(results) > 0.5
    )
    if outage:
        logger.warning(
            "RSS-Ausfall erkannt (%d von %d Feeds fehlgeschlagen) - "
            "Fehlzaehler bleiben unveraendert",
            sum(1 for _, kind, _ in results if kind != "ok"),
            len(results),
        )

    for index, (channel_id, kind, payload) in enumerate(results, start=1):
        channel = by_id[channel_id]
        if kind == "ok":
            try:
                feed = rss.parse_feed(payload)
            except rss.FeedError as exc:
                kind, payload = "error", str(exc)
            else:
                new_videos += _apply_feed(conn, channel, feed)
                if index % 25 == 0:
                    conn.commit()
                continue

        failed += 1
        if outage:
            if index % 25 == 0:
                conn.commit()
            continue

        fail_streak = channel["fail_streak"] + 1
        logger.info(
            "Feed %s fehlgeschlagen (%s: %s), Versuch %d",
            channel_id,
            kind,
            str(payload)[:80],
            fail_streak,
        )
        _apply_failure(conn, channel, fail_streak)
        if index % 25 == 0:
            conn.commit()

    conn.commit()
    enforce_caps(conn)
    conn.commit()

    stats = {"polled": len(results), "new_videos": new_videos, "failed": failed, "outage": outage}
    logger.info(
        "Poll-Zyklus: %(polled)s Feeds, %(new_videos)s neue Kandidaten, "
        "%(failed)s Fehler" % stats
    )
    return stats


def _enrich_forever() -> None:
    """Laufzeiten nachtragen, unabhaengig vom (langsamen) RSS-Zyklus."""
    from . import enrich

    conn = db.connect()
    while True:
        try:
            if db.remaining_quota(conn) > 500:
                enrich.enrich_batch(conn, limit=200)
        except Exception:  # pragma: no cover - nur Logging
            logger.exception("Enricher-Fehler")
        time.sleep(30)


def _archive_forever() -> None:
    """Internet-Archive-Kandidaten nachziehen (kein API-Quota)."""
    from . import archive

    conn = db.connect()
    while True:
        try:
            archive.discover(conn)
        except Exception:  # pragma: no cover - nur Logging
            logger.exception("Archive-Discovery fehlgeschlagen")
        time.sleep(config.ARCHIVE_INTERVAL)


def _thumb_forever() -> None:
    """Platzhalter-Vorschaubilder durch echte Frames ersetzen."""
    from . import archive

    conn = db.connect()
    while True:
        try:
            archive.refresh_thumbnails(conn, limit=8)
        except Exception:  # pragma: no cover - nur Logging
            logger.exception("Thumbnail-Reparatur fehlgeschlagen")
        time.sleep(45)


def run(once: bool = False, dry_run: bool = False) -> None:
    from . import enrich

    conn = db.connect()

    if once:
        if not dry_run and db.remaining_quota(conn) > 500:
            enrich.enrich_batch(conn, limit=200)
        poll_cycle(conn, dry_run=dry_run)
        return

    threading.Thread(target=_enrich_forever, daemon=True).start()
    if config.ARCHIVE_ENABLED:
        threading.Thread(target=_archive_forever, daemon=True).start()
        threading.Thread(target=_thumb_forever, daemon=True).start()

    last_prune = 0.0
    while True:
        stats = poll_cycle(conn, dry_run=dry_run)

        # Alle fuenf Minuten alles loeschen, was nie wieder ausgeliefert wird.
        if time.time() - last_prune > 300:
            last_prune = time.time()
            try:
                removed = db.prune_consumed(conn)
                if removed:
                    logger.info("%d verbrauchte Zeilen entfernt", removed)
            except Exception:  # pragma: no cover - nur Logging
                logger.exception("Prune fehlgeschlagen")

        if stats.get("outage"):
            time.sleep(120)
        else:
            time.sleep(5 if stats.get("polled") else 15)
