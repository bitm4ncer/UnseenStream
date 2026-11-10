from datetime import timedelta
from pathlib import Path

from app import api, db


def _insert_video(
    conn,
    video_id,
    views,
    age_hours=3,
    duration=600,
    provider="youtube",
    channel_id="UCtest",
):
    now = db.utcnow()
    media_url = (
        f"https://archive.org/download/{video_id}/v.mp4"
        if provider == "archive"
        else None
    )
    conn.execute(
        """
        INSERT INTO videos (id, channel_id, channel_title, title, thumbnail,
                            views, published_at, discovered_at, last_seen,
                            source, duration_s, provider, media_url)
        VALUES (?, ?, 'Kanal', ?, 'https://example.invalid/t.jpg', ?,
                ?, ?, ?, 'rss', ?, ?, ?)
        """,
        (
            video_id,
            channel_id,
            f"Titel {video_id}",
            views,
            db.iso(now - timedelta(hours=age_hours)),
            db.iso(now),
            db.iso(now),
            duration,
            provider,
            media_url,
        ),
    )
    conn.commit()


def _reset_pool():
    api.pool._loaded_at = 0.0
    api.pool._items = []
    api.pool._weights = []


def test_empty_pool_returns_503(connection):
    _reset_pool()
    client = api.app.test_client()

    response = client.get("/current-video")
    assert response.status_code == 503
    assert response.get_json()["error"] == "no_videos"


def test_only_zero_view_videos_are_served(connection):
    _reset_pool()
    _insert_video(connection, "zero", 0)
    _insert_video(connection, "one", 1)
    _insert_video(connection, "hundred", 100)

    client = api.app.test_client()
    payload = client.get("/current-video").get_json()

    assert payload["id"] == "zero"


def test_too_young_videos_are_not_served(connection):
    _reset_pool()
    _insert_video(connection, "young", 0, age_hours=1)
    _insert_video(connection, "old_enough", 0, age_hours=3)

    client = api.app.test_client()
    payload = client.get("/current-video").get_json()

    assert payload["id"] == "old_enough"


def test_shorts_are_excluded(connection):
    _reset_pool()
    _insert_video(connection, "short", 0, duration=45)
    _insert_video(connection, "borderline", 0, duration=180)
    _insert_video(connection, "long", 0, duration=181)
    _insert_video(connection, "unknown", 0, duration=None)

    client = api.app.test_client()
    payload = client.get("/current-video").get_json()

    assert payload["id"] == "long"


def test_stale_videos_are_not_served(connection):
    _reset_pool()
    _insert_video(connection, "fresh", 0, age_hours=3)
    _insert_video(connection, "stale", 0, age_hours=3000)

    client = api.app.test_client()
    payload = client.get("/current-video").get_json()

    assert payload["id"] == "fresh"


def test_excluded_ids_are_respected(connection):
    _reset_pool()
    _insert_video(connection, "a", 0)
    _insert_video(connection, "b", 0)

    client = api.app.test_client()
    payload = client.post(
        "/current-video", json={"excluded_ids": ["a"]}
    ).get_json()

    assert payload["id"] == "b"


def test_all_excluded_falls_back_to_pool(connection):
    _reset_pool()
    _insert_video(connection, "only", 0)

    client = api.app.test_client()
    payload = client.post(
        "/current-video", json={"excluded_ids": ["only"]}
    ).get_json()

    assert payload["id"] == "only"


def test_source_filter_limits_provider(connection):
    _reset_pool()
    _insert_video(connection, "yt", 0, provider="youtube")
    _insert_video(connection, "ar", 0, provider="archive")

    client = api.app.test_client()
    payload = client.post("/current-video", json={"source": "archive"}).get_json()

    assert payload["id"] == "ar"
    assert payload["provider"] == "archive"


def test_video_is_consumed_after_first_serve(connection):
    _reset_pool()
    _insert_video(connection, "a", 0)
    _insert_video(connection, "b", 0)

    client = api.app.test_client()
    first = client.get("/current-video").get_json()["id"]
    second = client.get("/current-video").get_json()["id"]

    assert first != second
    assert client.get("/current-video").status_code == 503

    assert connection.execute(
        "SELECT COUNT(*) FROM videos WHERE served = 1"
    ).fetchone()[0] == 2


def test_consumed_videos_stay_gone_after_refresh(connection):
    _reset_pool()
    _insert_video(connection, "a", 0)

    client = api.app.test_client()
    client.get("/current-video")

    _reset_pool()  # Cache verwerfen, aus der DB neu laden
    assert api.pool.pick() is None


def test_source_filter_empty_provider_returns_503(connection):
    _reset_pool()
    _insert_video(connection, "yt", 0, provider="youtube")

    client = api.app.test_client()
    response = client.post("/current-video", json={"source": "archive"})

    assert response.status_code == 503


def test_exclude_channels_avoids_recent_uploader(connection):
    _reset_pool()
    _insert_video(connection, "a", 0, channel_id="UCa")
    _insert_video(connection, "b", 0, channel_id="UCb")

    client = api.app.test_client()
    payload = client.post(
        "/current-video", json={"exclude_channels": ["UCa"]}
    ).get_json()

    assert payload["id"] == "b"
    assert payload["channelId"] == "UCb"


def test_exclude_channels_falls_back_when_all_match(connection):
    _reset_pool()
    _insert_video(connection, "a", 0, channel_id="UCa")

    client = api.app.test_client()
    payload = client.post(
        "/current-video", json={"exclude_channels": ["UCa"]}
    ).get_json()

    assert payload["id"] == "a"


def test_unseen_count_matches_pool(connection):
    _reset_pool()
    _insert_video(connection, "a", 0)
    _insert_video(connection, "b", 0)
    _insert_video(connection, "viewed", 5)

    client = api.app.test_client()
    assert client.get("/unseen-count").get_json()["count"] == 2

    client.get("/current-video")
    assert client.get("/unseen-count").get_json()["count"] == 1


def test_unseen_count_is_not_cached(connection):
    _reset_pool()
    _insert_video(connection, "a", 0)

    client = api.app.test_client()
    response = client.get("/unseen-count")

    assert response.headers["Cache-Control"] == "no-store"


def test_exclude_channels_falls_back_to_recent_ten(connection):
    _reset_pool()
    _insert_video(connection, "a", 0, channel_id="UCa")

    client = api.app.test_client()
    payload = client.post(
        "/current-video",
        # UCa steht ganz hinten: die volle Sperre wuerde alles blocken, die
        # Zehner-Regel laesst UCa wieder zu.
        json={"exclude_channels": [f"UC{i}" for i in range(20)] + ["UCa"]},
    ).get_json()

    assert payload["id"] == "a"


def test_age_weight_prefers_older_videos():
    now = db.utcnow()
    young = api.age_weight(db.iso(now - timedelta(hours=2)), now)
    old = api.age_weight(db.iso(now - timedelta(days=30)), now)

    assert old > young
    assert 30.9 < old < 31.1


def test_sort_weights_inverts_age_preference():
    weights = [1.0, 900.0, api.AGE_WEIGHT_CAP + 1]

    assert api.sort_weights(weights, "old") == weights
    inverted = api.sort_weights(weights, "new")

    # Neuestes (kleinstes Gewicht) wird am wahrscheinlichsten.
    assert inverted[0] == api.AGE_WEIGHT_CAP + 1
    assert inverted[-1] == 1.0


def test_unseen_count_can_filter_by_source(connection):
    _reset_pool()
    _insert_video(connection, "yt", 0, provider="youtube")
    _insert_video(connection, "ar", 0, provider="archive")

    client = api.app.test_client()

    assert client.get("/unseen-count").get_json()["count"] == 2
    assert client.get("/unseen-count?source=archive").get_json()["count"] == 1
    assert client.get("/unseen-count?source=youtube").get_json()["count"] == 1


def test_source_filter_accepts_csv(connection):
    _reset_pool()
    _insert_video(connection, "yt", 0, provider="youtube")
    _insert_video(connection, "ar", 0, provider="archive")

    client = api.app.test_client()
    payload = client.post(
        "/current-video", json={"source": "youtube,archive"}
    ).get_json()

    assert payload["provider"] in ("youtube", "archive")


def test_unseen_count_accepts_csv(connection):
    _reset_pool()
    _insert_video(connection, "yt", 0, provider="youtube")
    _insert_video(connection, "ar", 0, provider="archive")

    client = api.app.test_client()

    assert (
        client.get("/unseen-count?source=youtube,archive").get_json()["count"]
        == 2
    )


def test_download_unknown_video_returns_404(connection):
    client = api.app.test_client()

    assert client.get("/download/does-not-exist").status_code == 404


def test_download_archive_redirects_to_file(connection):
    _insert_video(connection, "ar", 0, provider="archive")

    client = api.app.test_client()
    response = client.get("/download/ar")

    assert response.status_code == 302
    assert response.headers["Location"].startswith(
        "https://archive.org/download/"
    )


def test_download_youtube_streams_ytdlp(connection, monkeypatch, tmp_path):
    _insert_video(connection, "yt1", 0, provider="youtube")
    monkeypatch.setattr(api, "DOWNLOAD_DIR", tmp_path)

    class FakeResult:
        returncode = 0
        stderr = b""
        stdout = b""

    def fake_run(command, capture_output=True, timeout=0):
        target = command[command.index("-o") + 1].replace("%(ext)s", "mp4")
        Path(target).write_bytes(b"video-bytes")
        return FakeResult()

    monkeypatch.setattr(api.subprocess, "run", fake_run)

    client = api.app.test_client()
    response = client.get("/download/yt1")

    assert response.status_code == 200
    assert response.data == b"video-bytes"
    assert "attachment" in response.headers["Content-Disposition"]


def test_download_youtube_failure_returns_502(connection, monkeypatch, tmp_path):
    _insert_video(connection, "yt2", 0, provider="youtube")
    monkeypatch.setattr(api, "DOWNLOAD_DIR", tmp_path)

    class FakeResult:
        returncode = 1
        stderr = b"Sign in to confirm you are not a bot"
        stdout = b""

    monkeypatch.setattr(
        api.subprocess, "run", lambda *a, **k: FakeResult()
    )

    client = api.app.test_client()
    response = client.get("/download/yt2")

    assert response.status_code == 502
    assert response.get_json()["error"] == "download_failed"


def test_video_by_id_returns_shared_video(connection):
    _insert_video(connection, "shared", 0, provider="archive")

    client = api.app.test_client()
    payload = client.get("/video/shared").get_json()

    assert payload["id"] == "shared"
    assert payload["provider"] == "archive"


def test_video_by_id_unknown_returns_404(connection):
    client = api.app.test_client()

    assert client.get("/video/nope").status_code == 404


def test_old_host_serves_migration_page(connection):
    client = api.app.test_client()
    response = client.get(
        "/", headers={"Host": "unseenstream.bitmancer.net"}
    )

    assert response.status_code == 200
    assert b"has moved" in response.data
    assert b"unseen.bitmancer.net" in response.data


def test_response_includes_provider(connection):
    _reset_pool()
    _insert_video(connection, "ar", 0, provider="archive")

    client = api.app.test_client()
    payload = client.get("/current-video").get_json()

    assert payload["provider"] == "archive"


def test_health_reports_pool_and_channels(connection):
    _reset_pool()
    _insert_video(connection, "x", 0)

    client = api.app.test_client()
    payload = client.get("/health").get_json()

    assert payload["status"] == "healthy"
    assert payload["pool_size"] >= 1


def test_index_serves_frontend(connection):
    client = api.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"Unseen Stream" in response.data


def test_static_assets_are_served(connection):
    client = api.app.test_client()

    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200
