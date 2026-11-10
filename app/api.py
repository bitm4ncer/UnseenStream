"""HTTP-API: liefert zufaellige, kaum gesehene Videos aus dem Kandidatenpool."""

import logging
import random
import threading
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import config, db

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
app.logger.setLevel(logging.INFO)

_started_at = time.time()
_flush_thread_started = False
_served_lock = threading.Lock()
_served: Counter = Counter()


class CandidatePool:
    """Haelt die servierbaren Videos im Speicher und laedt sie periodisch neu."""

    def __init__(self, ttl: float = 20.0):
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._weights: list[int] = []
        self._loaded_at = 0.0
        self._ttl = ttl

    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._loaded_at < self._ttl:
            return

        with self._lock:
            if not force and now - self._loaded_at < self._ttl:
                return

            conn = db.connect()
            query = (
                "SELECT id, title, channel_title, thumbnail, views, "
                "published_at, provider "
                "FROM videos WHERE views <= ? AND duration_s > ?"
            )
            params: list = [config.SERVE_MAX_VIEWS, config.MIN_DURATION_S]

            if config.MIN_AGE_HOURS > 0:
                query += " AND published_at <= ?"
                params.append(
                    db.iso(db.utcnow() - timedelta(hours=config.MIN_AGE_HOURS))
                )

            if config.MAX_AGE_HOURS > 0:
                query += " AND published_at >= ?"
                params.append(
                    db.iso(db.utcnow() - timedelta(hours=config.MAX_AGE_HOURS))
                )

            query += " ORDER BY views ASC LIMIT ?"
            params.append(config.SERVE_MAX_PER_REQUEST)

            rows = conn.execute(query, params).fetchall()
            self._items = [dict(row) for row in rows]
            self._weights = [101 - min(int(row["views"]), 100) for row in rows]
            self._loaded_at = now

    def size(self) -> int:
        self.refresh()
        return len(self._items)

    def pick(
        self, excluded: set[str] | None = None, source: str | None = None
    ) -> dict | None:
        self.refresh()
        items = self._items
        if not items:
            return None

        pairs = list(zip(items, self._weights))
        wanted = source if source in ("youtube", "archive") else None

        if wanted:
            pairs = [(item, weight) for item, weight in pairs if item["provider"] == wanted]
        if excluded:
            remaining = [
                (item, weight) for item, weight in pairs if item["id"] not in excluded
            ]
            if remaining:
                pairs = remaining

        if not pairs:
            return None

        chosen = random.choices(
            [item for item, _ in pairs],
            weights=[weight for _, weight in pairs],
            k=1,
        )[0]
        return chosen


pool = CandidatePool()


def _record_served(video_id: str) -> None:
    with _served_lock:
        _served[video_id] += 1


def _flush_served_forever() -> None:
    while True:
        time.sleep(30)
        with _served_lock:
            if not _served:
                continue
            batch = list(_served.items())
            _served.clear()
        try:
            conn = db.connect()
            conn.executemany(
                "UPDATE videos SET served = served + ? WHERE id = ?",
                [(count, video_id) for video_id, count in batch],
            )
            conn.commit()
        except Exception:  # pragma: no cover - nur Logging
            logger.exception("Konnte served-Zaehler nicht schreiben")


def _start_background() -> None:
    global _flush_thread_started
    if _flush_thread_started:
        return
    _flush_thread_started = True
    threading.Thread(target=_flush_served_forever, daemon=True).start()


@app.before_request
def _ensure_background() -> None:
    _start_background()


@app.get("/health")
def health():
    conn = db.connect()
    channels = conn.execute(
        "SELECT COUNT(*) FROM channels WHERE alive = 1"
    ).fetchone()[0]
    candidates = pool.size()

    return jsonify(
        {
            "status": "healthy",
            "pool_size": candidates,
            "channels": channels,
            "last_discovery": db.get_meta(conn, "last_discovery"),
            "quota_today": db.spent_today(conn),
            "uptime_seconds": int(time.time() - _started_at),
        }
    )


@app.route("/current-video", methods=["GET", "POST"])
def current_video():
    excluded: set[str] = set()
    source = "all"
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        excluded = set(payload.get("excluded_ids") or [])
        source = payload.get("source") or "all"

    video = pool.pick(excluded, source)
    if video is None:
        return (
            jsonify(
                {
                    "error": "no_videos",
                    "message": "Keine Kandidaten im Pool. Der Poller fuellt ihn laufend.",
                    "retry_after": 15,
                }
            ),
            503,
        )

    _record_served(video["id"])
    return jsonify(
        {
            "id": video["id"],
            "title": video["title"],
            "channelTitle": video["channel_title"],
            "thumbnail": video["thumbnail"],
            "viewCount": video["views"],
            "publishedAt": video["published_at"],
            "provider": video["provider"],
        }
    )


@app.get("/stats")
def stats():
    conn = db.connect()
    tiers = {
        row["tier"]: row["count"]
        for row in conn.execute(
            "SELECT tier, COUNT(*) AS count FROM channels "
            "WHERE alive = 1 GROUP BY tier"
        )
    }
    providers = {
        row["provider"]: row["count"]
        for row in conn.execute(
            "SELECT provider, COUNT(*) AS count FROM videos GROUP BY provider"
        )
    }
    return jsonify(
        {
            "pool_size": pool.size(),
            "videos_by_provider": providers,
            "videos_total": conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
            "channels_by_tier": tiers,
            "quota_today": db.spent_today(conn),
            "quota_budget": config.DAILY_QUOTA,
            "last_discovery": db.get_meta(conn, "last_discovery"),
            "uptime_seconds": int(time.time() - _started_at),
        }
    )


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")
