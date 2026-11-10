"""Dailymotion als dritte Quelle.

Dailymotion liefert `views_total` direkt im Listen-Endpoint. Nach `recent`
sortiert ist der Tail voller Uploads mit 0 Aufrufen - genau die Videos, die
hier gesucht sind. Kein API-Key noetig, dafuer hoeflich crawlen.

Abspielbar ist Dailymotion nur per iframe: die Player-Metadaten liefern
HLS-Manifeste mit kurzlebigen `sec`-Tokens, die man nicht speichern kann.
Und der iframe braucht eine Player-ID aus dem Dailymotion Studio - ohne sie
antwortet Dailymotion auf fremden Domains mit 403 Forbidden.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from . import config, db

logger = logging.getLogger(__name__)

API_URL = "https://api.dailymotion.com/videos"
VIDEO_URL = "https://api.dailymotion.com/video/{video_id}"
# Dailymotion blockt Embeds auf nicht registrierten Domains (403). Der
# offizielle Weg ist der Player aus dem Studio, dessen ID den Embed freigibt.
PLAYER_URL = "https://geo.dailymotion.com/player/{player}.html?video={video_id}"
FIELDS = (
    "id,title,views_total,created_time,duration,"
    "thumbnail_480_url,owner.screenname"
)
PAGE_SIZE = 100

_session: requests.Session | None = None


def _http() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = config.API_USER_AGENT
    return _session


def search_recent(limit: int | None = None) -> list[dict]:
    """Frische Uploads (ab US_DAILYMOTION_FRESH_HOURS), 100 pro Seite."""
    rows = limit or config.DAILYMOTION_LIMIT
    after = int(
        (
            db.utcnow() - timedelta(hours=config.DAILYMOTION_FRESH_HOURS)
        ).timestamp()
    )

    docs: list[dict] = []
    page = 1
    while len(docs) < rows:
        response = _http().get(
            API_URL,
            params={
                "fields": FIELDS,
                "sort": "recent",
                "created_after": after,
                "limit": PAGE_SIZE,
                "page": page,
            },
            timeout=30,
        )
        response.raise_for_status()

        batch = response.json().get("list") or []
        if not batch:
            break

        docs.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        page += 1

    return docs[:rows]


def is_candidate(doc: dict) -> bool:
    """0 Aufrufe und eine Laenge, die ins Raster passt."""
    if int(doc.get("views_total") or 0) != 0:
        return False

    try:
        duration = int(doc.get("duration"))
    except (TypeError, ValueError):
        return False

    return config.MIN_DURATION_S < duration <= config.DAILYMOTION_MAX_DURATION_S


def embed_url(video_id: str) -> str:
    return PLAYER_URL.format(
        player=config.DAILYMOTION_PLAYER, video_id=video_id
    )


def _published_at(doc: dict) -> str | None:
    try:
        moment = datetime.fromtimestamp(
            int(doc.get("created_time")), timezone.utc
        )
    except (TypeError, ValueError):
        return None
    return db.iso(moment)


def _ingest(conn, docs: list[dict], now: str) -> tuple[int, int]:
    added = 0
    refreshed = 0

    for doc in docs:
        if not is_candidate(doc):
            continue

        video_id = str(doc.get("id") or "")
        if not video_id:
            continue

        key = f"dm:{video_id}"
        owner = doc.get("owner.screenname") or "Dailymotion"
        views = int(doc.get("views_total") or 0)

        known = conn.execute(
            "SELECT id FROM videos WHERE id = ?", (key,)
        ).fetchone()

        if known:
            # Aufrufe koennen inzwischen gestiegen sein: nachziehen. Die
            # Embed-URL mitziehen, falls die Player-ID geaendert wurde.
            conn.execute(
                "UPDATE videos SET views = ?, last_seen = ?, media_url = ? "
                "WHERE id = ?",
                (views, now, embed_url(video_id), key),
            )
            conn.commit()
            refreshed += 1
            continue

        conn.execute(
            """
            INSERT INTO videos
                (id, channel_id, channel_title, title, thumbnail, views,
                 published_at, discovered_at, last_seen, source, duration_s,
                 provider, media_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'dailymotion', ?, 'dailymotion', ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                key,
                owner,
                owner,
                doc.get("title") or video_id,
                doc.get("thumbnail_480_url"),
                views,
                _published_at(doc),
                now,
                now,
                doc.get("duration"),
                embed_url(video_id),
            ),
        )
        # Sofort committen: keine offene Transaktion ueber Netzwerk-Calls.
        conn.commit()
        added += 1

    conn.commit()
    return added, refreshed


def discover(conn, limit: int | None = None) -> dict:
    """Frische 0-Aufruf-Uploads einsammeln."""
    if not config.DAILYMOTION_PLAYER:
        # Ohne Player-ID liefert Dailymotion nur 403-Embeds: lieber nichts
        # einsammeln, als unspielbare Kandidaten auszuliefern.
        logger.warning(
            "Dailymotion ohne US_DAILYMOTION_PLAYER: Discovery pausiert"
        )
        return {"status": "no_player", "found": 0, "added": 0, "refreshed": 0}

    now = db.iso(db.utcnow())
    docs = search_recent(limit=limit)
    added, refreshed = _ingest(conn, docs, now)

    stats = {
        "found": len(docs),
        "added": added,
        "refreshed": refreshed,
    }
    if added or refreshed:
        logger.info(
            "Dailymotion: %(found)s Treffer, %(added)s neu, "
            "%(refreshed)s aktualisiert" % stats
        )
    return stats


def probe(video_id: str) -> bool:
    """Existiert das Video noch? 404 = geloescht oder gesperrt."""
    try:
        response = _http().get(
            VIDEO_URL.format(video_id=video_id),
            params={"fields": "id"},
            timeout=15,
        )
    except requests.RequestException:
        return False
    return response.status_code == 200


def verify(conn, limit: int = 500) -> int:
    """Zeilen entfernen, deren Video nicht mehr abrufbar ist."""
    rows = conn.execute(
        "SELECT id FROM videos "
        "WHERE provider = 'dailymotion' AND served = 0 "
        "ORDER BY last_seen ASC LIMIT ?",
        (limit,),
    ).fetchall()

    removed = 0
    now = db.iso(db.utcnow())
    for row in rows:
        video_id = row["id"].split(":", 1)[-1]
        if probe(video_id):
            # Reihum pruefen: erreichbare Zeilen wandern nach hinten.
            conn.execute(
                "UPDATE videos SET last_seen = ? WHERE id = ?",
                (now, row["id"]),
            )
            conn.commit()
        else:
            conn.execute("DELETE FROM videos WHERE id = ?", (row["id"],))
            conn.commit()
            removed += 1
        time.sleep(config.DAILYMOTION_DELAY)

    conn.commit()
    if removed:
        logger.info("%d nicht abrufbare Dailymotion-Videos entfernt", removed)
    return removed
