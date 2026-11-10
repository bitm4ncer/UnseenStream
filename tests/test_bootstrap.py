from app import bootstrap


def test_entries_map_api_items():
    items = [
        {
            "id": "vid1",
            "snippet": {
                "title": "Titel",
                "publishedAt": "2026-11-10T09:00:00Z",
                "channelTitle": "Kanal",
                "thumbnails": {"medium": {"url": "https://example.invalid/t.jpg"}},
            },
            "statistics": {"viewCount": "7"},
        },
        {
            "id": "vid2",
            "snippet": {
                "title": "Ohne Statistik",
                "publishedAt": "2026-11-09T09:00:00+00:00",
            },
        },
    ]

    entries = bootstrap._entries(items)

    assert [entry["id"] for entry in entries] == ["vid1", "vid2"]
    assert entries[0]["views"] == 7
    assert entries[0]["published_at"] == "2026-11-10T09:00:00Z"
    assert entries[1]["views"] == 0
    assert entries[1]["thumbnail"] is None
