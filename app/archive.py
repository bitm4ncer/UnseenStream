"""Internet Archive als zweite Quelle.

archive.org liefert keine "Views", aber `downloads` - und das ist direkt
filterbar. Ein frisch hochgeladenes Item mit `downloads: 0` ist damit der
reinstmoegliche Fall von "das hat noch niemand gesehen".

Kein API-Key, kein Tagesquota. Dafuer hoeflich crawlen: sequenziell mit
kurzer Pause, damit die Non-Profit-Infrastruktur nicht belastet wird.
"""

import logging
import re
import time
from datetime import timedelta

import requests

from . import config, db

logger = logging.getLogger(__name__)

SEARCH_URL = "https://archive.org/advancedsearch.php"
META_URL = "https://archive.org/metadata/{identifier}"
THUMB_URL = "https://archive.org/services/img/{identifier}"

VIDEO_FILE = re.compile(r"\.(mp4|webm|ogv|m4v)$", re.IGNORECASE)
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{path}"

_session: requests.Session | None = None


def _http() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = config.API_USER_AGENT
    return _session


def search_recent(hours: int | None = None, limit: int | None = None) -> list[dict]:
    """Filme mit 0 Downloads, die bereits alt genug zum Ausliefern sind.

    Das Fenster beginnt bei ``US_MIN_AGE_HOURS``, weil juengere Items beim
    Ausliefern ohnehin verworfen werden - sie werden spaeter erfasst, wenn
    sie in dieses Fenster hineinwachsen.
    """
    rows = limit or config.ARCHIVE_LIMIT
    end = db.iso(db.utcnow() - timedelta(hours=config.MIN_AGE_HOURS))
    start = db.iso(db.utcnow() - timedelta(hours=config.MAX_AGE_HOURS))

    params = {
        "q": (
            f"mediatype:movies AND downloads:0 "
            f"AND addeddate:[{start} TO {end}]"
        ),
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
        "rows": str(rows),
        "output": "json",
    }

    response = _http().get(SEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("response", {}).get("docs", [])


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

    files = [
        item
        for item in payload.get("files", [])
        if VIDEO_FILE.search(item.get("name", ""))
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

    return {
        "duration_s": duration,
        "size": int(main.get("size") or 0),
        "media_url": DOWNLOAD_URL.format(identifier=identifier, path=path),
    }


def _channel_title(doc: dict) -> str:
    uploader = doc.get("uploader")
    if uploader:
        return uploader
    collections = doc.get("collection") or []
    return collections[0] if collections else "archive.org"


def discover(conn, limit: int | None = None) -> dict:
    """Holt neue 0-Download-Items und legt sie als Kandidaten ab."""
    docs = search_recent(limit=limit)
    now = db.iso(db.utcnow())
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
        conn.commit()
        added += 1

    conn.commit()
    stats = {"found": len(docs), "added": added, "refreshed": refreshed}
    if added or refreshed:
        logger.info(
            "Archive: %(found)s Treffer, %(added)s neu, %(refreshed)s aktualisiert"
            % stats
        )
    return stats
