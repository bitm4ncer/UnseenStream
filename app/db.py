"""SQLite-Zugriff: Schema, Zeithelfer, Quota-Buchung."""

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id               TEXT PRIMARY KEY,
    title            TEXT,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT,
    last_poll        TEXT,
    tier             TEXT NOT NULL DEFAULT 'warm',
    polls            INTEGER NOT NULL DEFAULT 0,
    hits             INTEGER NOT NULL DEFAULT 0,
    hit_streak       INTEGER NOT NULL DEFAULT 0,
    polls_since_hit  INTEGER NOT NULL DEFAULT 0,
    fail_streak      INTEGER NOT NULL DEFAULT 0,
    backoff_until    TEXT,
    alive            INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_channels_due
    ON channels (alive, tier, last_poll);

CREATE TABLE IF NOT EXISTS videos (
    id             TEXT PRIMARY KEY,
    channel_id     TEXT,
    channel_title  TEXT,
    title          TEXT,
    thumbnail      TEXT,
    views          INTEGER NOT NULL DEFAULT 0,
    published_at   TEXT,
    discovered_at  TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    source         TEXT,
    served         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_videos_pool
    ON videos (views, published_at);
CREATE INDEX IF NOT EXISTS idx_videos_channel
    ON videos (channel_id);

CREATE TABLE IF NOT EXISTS quota (
    day   TEXT PRIMARY KEY,
    units INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_local = threading.local()
_schema_ready = False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def hours_ago(hours: int) -> str:
    return iso(utcnow() - timedelta(hours=hours))


def connect(path: str | None = None) -> sqlite3.Connection:
    """Verbindung fuer den aktuellen Thread (SQLite-Connections sind threadspezifisch)."""
    db_path = path or config.DB_PATH
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == db_path:
        return conn

    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()

    _local.conn = conn
    _local.path = db_path
    return conn


def quota_day(now: datetime | None = None) -> str:
    """YouTube-Quota resettet um Mitternacht in America/Los_Angeles."""
    moment = (now or utcnow()).astimezone(ZoneInfo("America/Los_Angeles"))
    return moment.strftime("%Y-%m-%d")


def spend(conn: sqlite3.Connection, units: int) -> None:
    day = quota_day()
    conn.execute(
        """
        INSERT INTO quota (day, units) VALUES (?, ?)
        ON CONFLICT(day) DO UPDATE SET units = units + excluded.units
        """,
        (day, units),
    )
    conn.commit()


def spent_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT units FROM quota WHERE day = ?", (quota_day(),)
    ).fetchone()
    return int(row["units"]) if row else 0


def remaining_quota(conn: sqlite3.Connection) -> int:
    return max(0, config.DAILY_QUOTA - spent_today(conn))


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
