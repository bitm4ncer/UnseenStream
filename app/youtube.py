"""Duenner Client fuer die YouTube Data API v3 (REST, ohne google-api-python-client)."""

import logging
import re

import requests

from . import config, db

logger = logging.getLogger(__name__)


class QuotaExceeded(RuntimeError):
    """Tagesquota der YouTube-API erschoepft."""


class ApiError(RuntimeError):
    """Sonstiger API-Fehler."""


def _get(conn, path: str, params: dict) -> dict:
    if not config.API_KEY:
        raise ApiError("YOUTUBE_API_KEY ist nicht gesetzt")

    params = dict(params)
    params["key"] = config.API_KEY

    try:
        response = requests.get(
            f"{config.YOUTUBE_API}/{path}",
            params=params,
            timeout=config.API_TIMEOUT,
            headers={"User-Agent": config.API_USER_AGENT},
        )
    except requests.RequestException as exc:
        raise ApiError(f"Netzwerkfehler: {exc}") from exc

    if response.status_code == 403:
        body = response.text or ""
        if "quotaExceeded" in body or "dailyLimitExceeded" in body:
            raise QuotaExceeded(body[:200])

    if not response.ok:
        raise ApiError(f"HTTP {response.status_code}: {response.text[:200]}")

    return response.json()


def search_videos(conn, term: str, published_after: str) -> list[dict]:
    """Sucht die neuesten Videos zu einem Begriff. Kostet 100 Units."""
    payload = _get(
        conn,
        "search",
        {
            "part": "snippet",
            "type": "video",
            "q": term,
            "maxResults": config.SEARCH_RESULTS,
            "order": "date",
            "publishedAfter": published_after,
        },
    )
    db.spend(conn, config.SEARCH_COST)
    return payload.get("items", [])


def fetch_videos(conn, video_ids: list[str]) -> list[dict]:
    """Holt Details zu bis zu 50 Videos. Kostet 1 Unit pro Aufruf."""
    if not video_ids:
        return []
    wants = ",".join(video_ids[: config.BATCH_SIZE])
    payload = _get(
        conn,
        "videos",
        {
            "part": "snippet,statistics,contentDetails",
            "id": wants,
            "maxResults": config.BATCH_SIZE,
        },
    )
    db.spend(conn, config.VIDEOS_COST)
    return payload.get("items", [])


_DURATION = re.compile(
    r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$"
)


def parse_duration(value: str | None) -> int | None:
    """ISO-8601-Dauer (PT1M30S) in Sekunden."""
    if not value:
        return None
    match = _DURATION.match(value)
    if not match:
        return None
    days, hours, minutes, seconds = match.groups()
    total = (
        int(days or 0) * 86400
        + int(hours or 0) * 3600
        + int(minutes or 0) * 60
        + float(seconds or 0)
    )
    return int(total)


def duration_of(item: dict) -> int | None:
    return parse_duration((item.get("contentDetails") or {}).get("duration"))


def view_count(item: dict) -> int:
    try:
        return int(item["statistics"].get("viewCount", 0))
    except (KeyError, AttributeError, TypeError, ValueError):
        return 0


def playlist_items(conn, playlist_id: str, max_results: int = 50) -> list[dict]:
    """Letzte Uploads einer Playlist. Kostet 1 Unit."""
    payload = _get(
        conn,
        "playlistItems",
        {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": max_results,
        },
    )
    db.spend(conn, config.VIDEOS_COST)
    return payload.get("items", [])


def uploads_playlist(channel_id: str) -> str:
    """Uploads-Playlist eines Channels: UC... -> UU..."""
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return channel_id
