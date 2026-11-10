"""HTTP-API: liefert zufaellige, kaum gesehene Videos aus dem Kandidatenpool."""

import logging
import mimetypes
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    request,
    send_from_directory,
    stream_with_context,
)

from . import config, db, youtube

logger = logging.getLogger(__name__)

YTDLP = shutil.which("yt-dlp") or "yt-dlp"

mimetypes.add_type("application/manifest+json", ".webmanifest")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
app.logger.setLevel(logging.INFO)

_NO_CACHE_TYPES = {
    "text/html",
    "text/css",
    "application/javascript",
    "text/javascript",
    "application/manifest+json",
}


@app.after_request
def _revalidate_assets(response):
    """HTML/JS/CSS immer revalidieren, sonst haengt Handys eine alte Version."""
    if response.mimetype in _NO_CACHE_TYPES:
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

_started_at = time.time()
_recent_refresh: dict[str, float] = {}


AGE_WEIGHT_CAP = 1825.0

PROVIDERS = ("youtube", "archive")


def parse_sources(value: str | None) -> set[str] | None:
    """``all``/leer -> None, sonst die gueltigen Provider aus einer CSV-Liste."""
    if not value or value == "all":
        return None

    wanted = {part.strip() for part in str(value).split(",")}
    wanted &= set(PROVIDERS)
    return wanted or None


def age_weight(published_at: str, now) -> float:
    """Aeltere Videos werden bevorzugt: 1 + Alter in Tagen (max. 60)."""
    try:
        age_hours = (now - db.parse_iso(published_at)).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1.0

    age_days = max(0.0, age_hours / 24)
    return 1.0 + min(age_days, AGE_WEIGHT_CAP)


def sort_weights(weights: list[float], sort: str | None) -> list[float]:
    """``new`` dreht die Altersgewichtung um: neueste zuerst."""
    if sort != "new":
        return weights
    return [2.0 + AGE_WEIGHT_CAP - weight for weight in weights]


class CandidatePool:
    """Haelt die servierbaren Videos im Speicher und laedt sie periodisch neu."""

    def __init__(self, ttl: float = 20.0):
        self._lock = threading.Lock()
        self._pick_lock = threading.Lock()
        self._items: list[dict] = []
        self._weights: list[float] = []
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
                "SELECT id, title, channel_id, channel_title, thumbnail, views, "
                "published_at, provider, media_url "
                "FROM videos WHERE views <= ? AND duration_s > ? AND served = 0 "
                "AND (provider != 'archive' "
                "OR media_url IS NOT NULL)"
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
            now_dt = db.utcnow()
            self._items = []
            for row in rows:
                item = dict(row)
                # Einheitlicher Schluessel fuer die Uploader-Sperre.
                item["channel_key"] = (
                    item.get("channel_id") or item.get("channel_title") or ""
                )
                self._items.append(item)
            self._weights = [age_weight(row["published_at"], now_dt) for row in rows]
            self._loaded_at = now

    def size(self, source: str | None = None) -> int:
        self.refresh()
        wanted = parse_sources(source)
        if wanted:
            return sum(1 for item in self._items if item["provider"] in wanted)
        return len(self._items)

    def pick(
        self,
        excluded: set[str] | None = None,
        source: str | None = None,
        exclude_channels: list[str] | None = None,
        sort: str | None = "old",
    ) -> dict | None:
        self.refresh()

        # Auswahl und Verbrauch muessen atomar sein, sonst bekommen zwei
        # gleichzeitige Requests dasselbe Video.
        with self._pick_lock:
            items = self._items
            if not items:
                return None

            pairs = list(zip(items, sort_weights(self._weights, sort)))
            wanted = parse_sources(source)

            if wanted:
                pairs = [
                    (item, weight)
                    for item, weight in pairs
                    if item["provider"] in wanted
                ]
            if excluded:
                remaining = [
                    (item, weight)
                    for item, weight in pairs
                    if item["id"] not in excluded
                ]
                if remaining:
                    pairs = remaining

            if exclude_channels:
                # Reihenfolge zaehlt: vorne stehen die zuletzt gesehenen.
                blocked = set(exclude_channels)
                remaining = [
                    (item, weight)
                    for item, weight in pairs
                    if item["channel_key"] not in blocked
                ]
                if remaining:
                    pairs = remaining
                elif len(exclude_channels) > 10:
                    # Pool zu klein fuer die volle Sperre: nur die letzten
                    # zehn Uploader ausnehmen, statt alles freizugeben.
                    blocked = set(exclude_channels[:10])
                    remaining = [
                        (item, weight)
                        for item, weight in pairs
                        if item["channel_key"] not in blocked
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

            # Global verbrauchen: das Video darf kein zweiter Nutzer bekommen.
            self._consume(chosen["id"])
            return chosen

    def _consume(self, video_id: str) -> None:
        with self._lock:
            for index, item in enumerate(self._items):
                if item["id"] == video_id:
                    del self._items[index]
                    del self._weights[index]
                    break


pool = CandidatePool()


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


def _download_name(title: str, video_id: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:80]
    cleaned = cleaned.encode("ascii", "ignore").decode().strip()
    return f"{cleaned or video_id}.mp4"


DOWNLOAD_DIR = Path(
    os.environ.get(
        "US_DOWNLOAD_DIR",
        "/data/downloads" if Path("/data").is_dir() else tempfile.gettempdir(),
    )
)


@app.get("/download/<video_id>")
def download(video_id):
    """YouTube laesst sich nur serverseitig holen, archive.org direkt."""
    conn = db.connect()
    row = conn.execute(
        "SELECT id, provider, title, media_url FROM videos WHERE id = ?",
        (video_id,),
    ).fetchone()

    if row is None:
        abort(404)

    if row["provider"] == "archive" and row["media_url"]:
        return redirect(row["media_url"])

    if row["provider"] != "youtube":
        abort(404)

    filename = _download_name(row["title"], video_id)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(dir=DOWNLOAD_DIR, prefix=f"{video_id}-"))

    command = [
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--socket-timeout",
        "20",
        "-f",
        "bv*[height<=720]+ba/b[height<=720]/b",
        "--merge-output-format",
        "mp4",
        "-o",
        str(workdir / "video.%(ext)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]

    # YouTube blockt Rechenzentrums-IPs sporadisch ("confirm you're not a bot").
    # tv_embedded umgeht das manchmal; mit Cookies aus dem eigenen Browser
    # ist es zuverlaessig.
    attempts = [
        [],
        ["--extractor-args", "youtube:player_client=tv_embedded"],
    ]

    if Path(config.YTDLP_COOKIES).is_file():
        for attempt in attempts:
            attempt.extend(["--cookies", config.YTDLP_COOKIES])

    result = None
    for extra in attempts:
        try:
            result = subprocess.run(
                [YTDLP, *extra, *command], capture_output=True, timeout=240
            )
        except FileNotFoundError:
            shutil.rmtree(workdir, ignore_errors=True)
            return jsonify({"error": "yt_dlp_missing"}), 503
        except subprocess.TimeoutExpired:
            continue

        if result.returncode == 0 and list(workdir.glob("video.*")):
            break

    produced = sorted(workdir.glob("video.*"))
    if result is None:
        shutil.rmtree(workdir, ignore_errors=True)
        return jsonify({"error": "download_timeout"}), 504

    if result.returncode != 0 or not produced:
        detail = result.stderr.decode("utf-8", "replace")[-300:]
        shutil.rmtree(workdir, ignore_errors=True)
        logger.warning("yt-dlp fehlgeschlagen: %s", detail)
        return jsonify({"error": "download_failed", "detail": detail}), 502

    path = produced[0]
    size = path.stat().st_size

    def generate():
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    yield chunk
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    return Response(
        stream_with_context(generate()),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Cache-Control": "no-store",
        },
    )


@app.get("/sources")
def sources():
    return jsonify({"providers": list(PROVIDERS)})


@app.get("/unseen-count")
def unseen_count():
    # Kostenlos: die Laenge des In-Memory-Pools, kein DB-Query solange der
    # Cache frisch ist (20 s TTL). Sinkt sofort beim Ausliefern.
    source = request.args.get("source")
    response = jsonify(
        {"count": pool.size(source)}
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/current-video", methods=["GET", "POST"])
def current_video():
    excluded: set[str] = set()
    exclude_channels: list[str] = []
    source = "all"
    sort = "old"
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        excluded = set(payload.get("excluded_ids") or [])
        exclude_channels = list(payload.get("exclude_channels") or [])
        source = payload.get("source") or "all"
        sort = payload.get("sort") or "old"

    video = pool.pick(excluded, source, exclude_channels, sort)
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

    # Sofort global verbrauchen, damit kein zweiter Nutzer das Video bekommt.
    conn = db.connect()

    # YouTube-Views veralten: beim Ausliefern frisch holen (1 Unit), damit
    # die Anzeige stimmt und Videos mit Views aus dem Pool fallen.
    if video["provider"] == "youtube" and db.remaining_quota(conn) > 100:
        try:
            fresh = youtube.fetch_views(conn, video["id"])
        except Exception:  # noqa: BLE001 - Anzeige darf nie das Serving brechen
            fresh = None

        if fresh is not None and fresh != video["views"]:
            conn.execute(
                "UPDATE videos SET views = ? WHERE id = ?", (fresh, video["id"])
            )
            conn.commit()
            video["views"] = fresh

    conn.execute(
        "UPDATE videos SET served = served + 1 WHERE id = ?", (video["id"],)
    )
    conn.commit()

    return jsonify(
        {
            "id": video["id"],
            "title": video["title"],
            "channelId": video["channel_key"],
            "channelTitle": video["channel_title"],
            "thumbnail": video["thumbnail"],
            "viewCount": video["views"],
            "publishedAt": video["published_at"],
            "provider": video["provider"],
            "mediaUrl": video["media_url"],
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


NEW_HOST = "unseen.bitmancer.net"
OLD_HOSTS = {"unseenstream.bitmancer.net"}


@app.get("/")
def index():
    """Alte Domain liefert die Umzugsseite, die localStorage mitnimmt."""
    host = (request.host or "").split(":")[0].lower()
    if host in OLD_HOSTS:
        return send_from_directory(WEB_DIR, "migrate.html")
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/video/<video_id>")
def video_by_id(video_id):
    """Ein einzelnes Video fuer geteilte Links, auch wenn es schon lief."""
    conn = db.connect()
    row = conn.execute(
        "SELECT id, title, channel_id, channel_title, thumbnail, views, "
        "published_at, provider, media_url FROM videos WHERE id = ?",
        (video_id,),
    ).fetchone()

    if row is None:
        return jsonify({"error": "not_found"}), 404

    views = row["views"]
    wants_refresh = request.args.get("refresh") in ("1", "true", "yes")

    if (
        wants_refresh
        and row["provider"] == "youtube"
        and db.remaining_quota(conn) > 100
    ):
        now = time.time()
        # Nicht haeufiger als alle 20 s pro Video, egal wie viele Tabs fragen.
        if now - _recent_refresh.get(video_id, 0) > 20:
            _recent_refresh[video_id] = now
            try:
                fresh = youtube.fetch_views(conn, video_id)
            except Exception:  # noqa: BLE001 - Anzeige darf nie brechen
                fresh = None

            if fresh is not None:
                conn.execute(
                    "UPDATE videos SET views = ? WHERE id = ?", (fresh, video_id)
                )
                conn.commit()
                views = fresh

    return jsonify(
        {
            "id": row["id"],
            "title": row["title"],
            "channelId": row["channel_id"] or row["channel_title"],
            "channelTitle": row["channel_title"],
            "thumbnail": row["thumbnail"],
            "viewCount": views,
            "publishedAt": row["published_at"],
            "provider": row["provider"],
            "mediaUrl": row["media_url"],
        }
    )
