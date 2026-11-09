from datetime import timedelta

from app import api, db


def _insert_video(conn, video_id, views, age_hours=1):
    now = db.utcnow()
    conn.execute(
        """
        INSERT INTO videos (id, channel_id, channel_title, title, thumbnail,
                            views, published_at, discovered_at, last_seen, source)
        VALUES (?, 'UCtest', 'Kanal', ?, 'https://example.invalid/t.jpg', ?,
                ?, ?, ?, 'rss')
        """,
        (
            video_id,
            f"Titel {video_id}",
            views,
            db.iso(now - timedelta(hours=age_hours)),
            db.iso(now),
            db.iso(now),
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


def test_only_low_view_videos_are_served(connection):
    _reset_pool()
    _insert_video(connection, "low", 0)
    _insert_video(connection, "mid", 100)
    _insert_video(connection, "high", 101)

    client = api.app.test_client()
    seen = set()
    for _ in range(40):
        payload = client.get("/current-video").get_json()
        seen.add(payload["id"])

    assert seen <= {"low", "mid"}
    assert "high" not in seen


def test_stale_videos_are_not_served(connection):
    _reset_pool()
    _insert_video(connection, "fresh", 0, age_hours=1)
    _insert_video(connection, "stale", 0, age_hours=500)

    client = api.app.test_client()
    ids = {client.get("/current-video").get_json()["id"] for _ in range(30)}

    assert ids == {"fresh"}


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


def test_health_reports_pool_and_channels(connection):
    _reset_pool()
    _insert_video(connection, "x", 0)

    client = api.app.test_client()
    payload = client.get("/health").get_json()

    assert payload["status"] == "healthy"
    assert payload["pool_size"] >= 1


def test_weighting_prefers_zero_view_videos(connection):
    _reset_pool()
    _insert_video(connection, "zero", 0)
    _insert_video(connection, "hundred", 100)

    counts = {"zero": 0, "hundred": 0}
    for _ in range(600):
        counts[api.pool.pick()["id"]] += 1

    assert counts["zero"] > counts["hundred"] * 5


def test_index_serves_frontend(connection):
    client = api.app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"Unseen Stream" in response.data


def test_static_assets_are_served(connection):
    client = api.app.test_client()

    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200
