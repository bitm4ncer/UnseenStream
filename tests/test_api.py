from datetime import timedelta

from app import api, db


def _insert_video(conn, video_id, views, age_hours=3, duration=600, provider="youtube"):
    now = db.utcnow()
    conn.execute(
        """
        INSERT INTO videos (id, channel_id, channel_title, title, thumbnail,
                            views, published_at, discovered_at, last_seen,
                            source, duration_s, provider)
        VALUES (?, 'UCtest', 'Kanal', ?, 'https://example.invalid/t.jpg', ?,
                ?, ?, ?, 'rss', ?, ?)
        """,
        (
            video_id,
            f"Titel {video_id}",
            views,
            db.iso(now - timedelta(hours=age_hours)),
            db.iso(now),
            db.iso(now),
            duration,
            provider,
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
    _insert_video(connection, "stale", 0, age_hours=500)

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
