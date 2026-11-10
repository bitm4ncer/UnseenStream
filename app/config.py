"""Zentrale Konfiguration, gelesen aus Umgebungsvariablen."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

DB_PATH = os.environ.get("US_DB_PATH", str(BASE_DIR / "data" / "unseenstream.db"))
SEARCH_TERMS_FILE = os.environ.get(
    "US_SEARCH_TERMS", str(BASE_DIR / "search_terms.txt")
)

# Auswahl
MAX_VIEWS = _int("US_MAX_VIEWS", 100)
SERVE_MAX_VIEWS = _int("US_SERVE_MAX_VIEWS", 0)
MIN_AGE_HOURS = _int("US_MIN_AGE_HOURS", 2)
MIN_DURATION_S = _int("US_MIN_DURATION_S", 180)
MAX_AGE_HOURS = _int("US_MAX_AGE_HOURS", 48)
SERVE_MAX_PER_REQUEST = _int("US_SERVE_MAX", 50000)

# Quota
DAILY_QUOTA = _int("US_DAILY_QUOTA", 9700)
SEARCH_COST = 100
VIDEOS_COST = 1
SEARCHES_PER_HOUR = _int("US_SEARCHES_PER_HOUR", 4)
SEARCH_WINDOW_HOURS = _int("US_SEARCH_WINDOW_HOURS", 6)
SEARCH_RESULTS = _int("US_SEARCH_RESULTS", 50)
BATCH_SIZE = 50

# Tiering
TIERS = {
    "hot": {
        "interval": _int("US_HOT_INTERVAL", 600),
        "cap": _int("US_HOT_CAP", 100),
    },
    "warm": {
        "interval": _int("US_WARM_INTERVAL", 3600),
        "cap": _int("US_WARM_CAP", 1000),
    },
    "cold": {
        "interval": _int("US_COLD_INTERVAL", 21600),
        "cap": _int("US_COLD_CAP", 5000),
    },
}
TIER_ORDER = ("hot", "warm", "cold")
PROMOTE_AFTER_STREAK = 2
DEMOTE_HOT_AFTER = 6
DEMOTE_WARM_AFTER = 20
DEAD_AFTER_FAILS = 5
POLL_BATCH = {
    "hot": _int("US_POLL_BATCH_HOT", 100),
    "warm": _int("US_POLL_BATCH_WARM", 200),
    "cold": _int("US_POLL_BATCH_COLD", 300),
}

# Netzwerk
POLL_WORKERS = _int("US_POLL_WORKERS", 8)
POLL_RATE = _float("US_POLL_RATE", 5.0)
FEED_TIMEOUT = _int("US_FEED_TIMEOUT", 10)
API_TIMEOUT = _int("US_API_TIMEOUT", 20)

USER_AGENT = os.environ.get(
    "US_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
)
API_USER_AGENT = os.environ.get("US_API_USER_AGENT", "UnseenStream/1.0")

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

# Internet Archive als zweite Quelle
ARCHIVE_ENABLED = os.environ.get("US_ARCHIVE_ENABLED", "1") not in ("0", "false", "False")
ARCHIVE_LIMIT = _int("US_ARCHIVE_LIMIT", 200)
ARCHIVE_INTERVAL = _int("US_ARCHIVE_INTERVAL", 600)
ARCHIVE_WINDOW_HOURS = _int("US_ARCHIVE_WINDOW_HOURS", 3)
ARCHIVE_DELAY = _float("US_ARCHIVE_DELAY", 0.2)
