"""Duenner Client fuer die YouTube Data API v3 (REST, ohne google-api-python-client)."""

import logging

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
        {"part": "snippet,statistics", "id": wants, "maxResults": config.BATCH_SIZE},
    )
    db.spend(conn, config.VIDEOS_COST)
    return payload.get("items", [])


def view_count(item: dict) -> int:
    try:
        return int(item["statistics"].get("viewCount", 0))
    except (KeyError, AttributeError, TypeError, ValueError):
        return 0
