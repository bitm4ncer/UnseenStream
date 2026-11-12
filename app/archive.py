"""Internet Archive als zweite Quelle.

archive.org liefert keine "Views", aber `downloads` - und das ist direkt
filterbar. Ein frisch hochgeladenes Item mit `downloads: 0` ist damit der
reinstmoegliche Fall von "das hat noch niemand gesehen".

Kein API-Key, kein Tagesquota. Dafuer hoeflich crawlen: sequenziell mit
kurzer Pause, damit die Non-Profit-Infrastruktur nicht belastet wird.
"""

import base64
import logging
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone

import requests

from . import config, db

logger = logging.getLogger(__name__)

SEARCH_URL = "https://archive.org/advancedsearch.php"
META_URL = "https://archive.org/metadata/{identifier}"
THUMB_URL = "https://archive.org/services/img/{identifier}"

VIDEO_FILE = re.compile(r"\.(mp4|webm|ogv|m4v)$", re.IGNORECASE)
# Nur Container, die ein Browser ohne Plugin abspielen kann.
PLAYABLE_FILE = re.compile(r"\.(mp4|webm|m4v)$", re.IGNORECASE)
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{path}"

# archive.org liefert fuer Items ohne echtes Vorschaubild ein generisches
# PNG mit exakt dieser Groesse. Alles andere ist ein echter Frame.
PLACEHOLDER_BYTES = 3777

_session: requests.Session | None = None


def _http() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = config.API_USER_AGENT
    return _session


def _search(query: str, limit: int) -> list[dict]:
    params = {
        "q": query,
        "fl[]": [
            "identifier",
            "title",
            "addeddate",
            "downloads",
            "item_size",
            "collection",
            "uploader",
        ],
        "sort[]": "addeddate desc",
        "rows": str(limit),
        "output": "json",
    }

    response = _http().get(SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("response", {}).get("docs", [])


def search_recent(limit: int | None = None) -> list[dict]:
    """Frische Filme mit 0 Downloads (ab US_MIN_AGE_HOURS)."""
    rows = limit or config.ARCHIVE_LIMIT
    end = db.iso(db.utcnow() - timedelta(hours=config.MIN_AGE_HOURS))
    start = db.iso(db.utcnow() - timedelta(hours=config.ARCHIVE_FRESH_HOURS))

    return _search(
        f"mediatype:movies AND downloads:0 AND addeddate:[{start} TO {end}]", rows
    )


def search_deep(cursor: str | None = None, limit: int | None = None) -> list[dict]:
    """Alte, nie geoeffnete Filme: vom Cursor rueckwaerts bis zu DEEP_DAYS."""
    rows = limit or config.ARCHIVE_DEEP_LIMIT
    start = db.iso(db.utcnow() - timedelta(days=config.ARCHIVE_DEEP_DAYS))
    end = cursor or db.iso(
        db.utcnow() - timedelta(hours=config.ARCHIVE_FRESH_HOURS)
    )

    return _search(
        f"mediatype:movies AND downloads:0 AND addeddate:[{start} TO {end}]", rows
    )


def fetch_metadata(identifier: str) -> dict | None:
    """Laufzeit, Groesse und Download-URL der besten abspielbaren Datei."""
    try:
        response = _http().get(META_URL.format(identifier=identifier), timeout=20)
    except requests.RequestException as exc:
        logger.debug("Metadaten %s: %s", identifier, exc)
        return None

    if response.status_code != 200:
        return None

    try:
        payload = response.json()
    except ValueError:
        return None

    if str(payload.get("metadata", {}).get("access-restricted-item", "")).lower() == "true":
        return None

    files = [
        item
        for item in payload.get("files", [])
        if PLAYABLE_FILE.search(item.get("name", ""))
        and str(item.get("private", "")).lower() != "true"
    ]
    if not files:
        return None

    # MP4 zuerst (beste Browser-Unterstuetzung), dann nach Groesse.
    files.sort(
        key=lambda item: (
            item.get("name", "").lower().endswith(".mp4"),
            int(item.get("size") or 0),
        ),
        reverse=True,
    )
    main = files[0]

    length = main.get("length")
    duration = None
    if length:
        try:
            duration = int(float(length))
        except (TypeError, ValueError):
            duration = None

    path = "/".join(
        requests.utils.quote(part) for part in main.get("name", "").split("/")
    )
    canonical = DOWNLOAD_URL.format(identifier=identifier, path=path)

    # Direkte Node-URL spart den 302 von archive.org (rund eine halbe
    # Sekunde vor dem ersten Byte). Faellt der Node weg, bleibt /download.
    server = payload.get("server")
    node_dir = payload.get("dir")
    direct = f"https://{server}{node_dir}/{path}" if server and node_dir else None

    media_url = None
    for candidate in (direct, canonical):
        if candidate and probe_media(candidate):
            media_url = candidate
            break

    if not media_url:
        logger.debug("Archive-Datei nicht abrufbar: %s", canonical)
        return None

    return {
        "duration_s": duration,
        "size": int(main.get("size") or 0),
        "media_url": media_url,
        "download_url": canonical,
    }


def probe_media(url: str) -> bool:
    """Kurz pruefen, ob die Datei wirklich ausgeliefert wird.

    Access-restricted Items liefern trotz Eintrag in den Metadaten eine
    403-HTML-Seite. Ohne diesen Check landet sowas im Pool und der Player
    springt endlos weiter.
    """
    try:
        response = _http().get(
            url, headers={"Range": "bytes=0-1"}, timeout=15, stream=True
        )
    except requests.RequestException:
        return False

    try:
        if response.status_code not in (200, 206):
            return False
        content_type = response.headers.get("Content-Type", "").lower()
        return content_type.startswith(("video/", "application/octet-stream"))
    finally:
        response.close()


def thumb_is_placeholder(identifier: str) -> bool:
    """True, wenn archive.org nur das generische Vorschaubild liefert."""
    try:
        response = _http().get(THUMB_URL.format(identifier=identifier), timeout=15)
    except requests.RequestException:
        return False

    if response.status_code != 200:
        return False

    return len(response.content) == PLACEHOLDER_BYTES


def extract_frame(media_url: str, position: int = 3) -> str | None:
    """Erstes brauchbares Bild als data-URI, direkt aus dem MP4."""
    for seek in (position, 0):
        command = [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-ss",
            str(seek),
            "-i",
            media_url,
            "-frames:v",
            "1",
            "-vf",
            "scale=480:-2",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, timeout=45, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ffmpeg fehlgeschlagen: %s", exc)
            return None

        if result.returncode == 0 and result.stdout:
            encoded = base64.b64encode(result.stdout).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"

    return None


def refresh_thumbnails(conn, limit: int = 8) -> int:
    """Ersetzt Platzhalter-Vorschaubilder durch einen echten Videoframe."""
    rows = conn.execute(
        "SELECT id, media_url FROM videos "
        "WHERE provider = 'archive' AND thumb_checked = 0 "
        "AND media_url IS NOT NULL "
        "ORDER BY (served = 0 AND views = 0) DESC, published_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    fixed = 0
    for row in rows:
        if not thumb_is_placeholder(row["id"]):
            conn.execute(
                "UPDATE videos SET thumb_checked = 1 WHERE id = ?", (row["id"],)
            )
            conn.commit()
            continue

        frame = extract_frame(row["media_url"])
        if frame:
            conn.execute(
                "UPDATE videos SET thumbnail = ?, thumb_checked = 1 WHERE id = ?",
                (frame, row["id"]),
            )
            fixed += 1
        else:
            # Nicht ewig wiederholen: 2 = aufgegeben.
            conn.execute(
                "UPDATE videos SET thumb_checked = 2 WHERE id = ?", (row["id"],)
            )
        conn.commit()
        time.sleep(0.3)

    if fixed:
        logger.info("%d Vorschaubilder aus Videoframes erzeugt", fixed)
    return fixed


def verify_archive(conn, limit: int = 500) -> int:
    """Entfernt Archive-Zeilen, deren Datei nicht mehr abrufbar ist."""
    rows = conn.execute(
        "SELECT id, media_url FROM videos "
        "WHERE provider='archive' AND media_url IS NOT NULL AND served=0 LIMIT ?",
        (limit,),
    ).fetchall()

    removed = 0
    for row in rows:
        if not probe_media(row["media_url"]):
            conn.execute("DELETE FROM videos WHERE id = ?", (row["id"],))
            conn.commit()
            removed += 1
        time.sleep(0.1)

    conn.commit()
    if removed:
        logger.info("%d nicht abrufbare Archive-Items entfernt", removed)
    return removed


def search_vintage(
    year: int, cursor: str | None = None, limit: int | None = None
) -> list[dict]:
    """Ein komplettes Jahr nach 0-Download-Items absuchen."""
    rows = limit or config.ARCHIVE_VINTAGE_LIMIT
    start = db.iso(datetime(year, 1, 1, tzinfo=timezone.utc))
    end = cursor or db.iso(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))

    return _search(
        f"mediatype:movies AND downloads:0 AND addeddate:[{start} TO {end}]", rows
    )


def _channel_title(doc: dict) -> str:
    uploader = doc.get("uploader")
    if uploader:
        return uploader
    collections = doc.get("collection") or []
    return collections[0] if collections else "archive.org"


def _ingest(conn, docs: list[dict], now: str) -> tuple[int, int]:
    added = 0
    refreshed = 0

    for doc in docs:
        identifier = doc.get("identifier")
        if not identifier:
            continue

        known = conn.execute(
            "SELECT id, media_url FROM videos WHERE id = ?", (identifier,)
        ).fetchone()

        downloads = int(doc.get("downloads") or 0)

        if known:
            if known["media_url"]:
                # Downloads koennen inzwischen gestiegen sein: nachziehen.
                conn.execute(
                    "UPDATE videos SET views = ?, last_seen = ? WHERE id = ?",
                    (downloads, now, identifier),
                )
                conn.commit()
                refreshed += 1
                continue

            # Alte Zeilen ohne direkte Medien-URL nachruesten.
            meta = fetch_metadata(identifier)
            time.sleep(config.ARCHIVE_DELAY)
            if meta:
                conn.execute(
                    "UPDATE videos SET views = ?, last_seen = ?, duration_s = ?, "
                    "media_url = ? WHERE id = ?",
                    (downloads, now, meta["duration_s"], meta["media_url"], identifier),
                )
                conn.commit()
                refreshed += 1
            continue

        meta = fetch_metadata(identifier)
        time.sleep(config.ARCHIVE_DELAY)
        if not meta:
            continue

        conn.execute(
            """
            INSERT INTO videos
                (id, channel_id, channel_title, title, thumbnail, views,
                 published_at, discovered_at, last_seen, source, duration_s,
                 provider, media_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'archive', ?, 'archive', ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                identifier,
                doc.get("uploader"),
                _channel_title(doc),
                doc.get("title") or identifier,
                THUMB_URL.format(identifier=identifier),
                downloads,
                db.normalize_ts(doc.get("addeddate")),
                now,
                now,
                meta["duration_s"],
                meta["media_url"],
            ),
        )
        added += 1

        # Sofort committen: die Transaktion darf nie ueber einen
        # Netzwerk-Call offen bleiben, sonst blockiert sie Poller und API.
        conn.commit()

    conn.commit()
    return added, refreshed


def discover(conn, limit: int | None = None) -> dict:
    """Frische Items plus alte, nie geoeffnete Items aus dem Deep-Fenster."""
    now = db.iso(db.utcnow())

    fresh = search_recent(limit=limit)
    added, refreshed = _ingest(conn, fresh, now)

    deep = search_deep(
        cursor=db.get_meta(conn, "archive_deep_cursor"),
        limit=config.ARCHIVE_DEEP_LIMIT,
    )
    deep_added, deep_refreshed = 0, 0
    if deep:
        deep_added, deep_refreshed = _ingest(conn, deep, now)

        oldest = min(
            (doc.get("addeddate") for doc in deep if doc.get("addeddate")),
            default=None,
        )
        if oldest:
            # Eine Sekunde zurueck, damit der Cursor nicht am selben
            # Item kleben bleibt.
            try:
                next_cursor = db.parse_iso(oldest) - timedelta(seconds=1)
                db.set_meta(conn, "archive_deep_cursor", db.iso(next_cursor))
            except (TypeError, ValueError):
                pass
            conn.commit()
    else:
        # Fenster durchgelaufen: beim naechsten Mal wieder vorne beginnen.
        db.set_meta(
            conn,
            "archive_deep_cursor",
            db.iso(db.utcnow() - timedelta(hours=config.ARCHIVE_FRESH_HOURS)),
        )
        conn.commit()

    # Ein Jahr pro Lauf komplett nach alten 0-Download-Items absuchen.
    year = int(
        db.get_meta(conn, "archive_vintage_year") or config.ARCHIVE_VINTAGE_START
    )
    cursor_key = f"archive_vintage_cursor_{year}"
    vintage = search_vintage(
        year, db.get_meta(conn, cursor_key), config.ARCHIVE_VINTAGE_LIMIT
    )
    vintage_added = 0
    if vintage:
        vintage_added, _ = _ingest(conn, vintage, now)
        oldest = min(
            (doc.get("addeddate") for doc in vintage if doc.get("addeddate")),
            default=None,
        )
        if oldest:
            try:
                next_cursor = db.parse_iso(oldest) - timedelta(seconds=1)
                db.set_meta(conn, cursor_key, db.iso(next_cursor))
            except (TypeError, ValueError):
                pass
            conn.commit()
    else:
        next_year = year - 1
        if next_year < config.ARCHIVE_VINTAGE_END:
            next_year = config.ARCHIVE_VINTAGE_START
        db.set_meta(conn, "archive_vintage_year", str(next_year))
        conn.commit()
        logger.info("Archive-Jahr %d abgeschlossen, weiter mit %d", year, next_year)

    stats = {
        "found": len(fresh) + len(deep) + len(vintage),
        "added": added + deep_added + vintage_added,
        "refreshed": refreshed + deep_refreshed,
        "deep": len(deep),
        "vintage": len(vintage),
        "year": year,
    }
    if stats["added"] or stats["refreshed"]:
        logger.info(
            "Archive: %(found)s Treffer (%(deep)s deep), %(added)s neu, "
            "%(refreshed)s aktualisiert" % stats
        )
    return stats
