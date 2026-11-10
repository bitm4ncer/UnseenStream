"""Ergaenzt fehlende Laufzeiten.

RSS-Feeds enthalten keine Video-Dauer, und ohne Dauer laesst sich Shorts
nicht ausschliessen. Der Enricher holt sie gebuendelt nach (1 Unit pro 50)
und markiert endgueltig unbekannte Videos mit -1, damit sie nicht erneut
abgefragt werden.
"""

import logging

from . import config, db, youtube

logger = logging.getLogger(__name__)


def enrich_batch(conn, limit: int = 500) -> int:
    rows = conn.execute(
        "SELECT id FROM videos WHERE duration_s IS NULL LIMIT ?", (limit,)
    ).fetchall()
    if not rows:
        return 0

    ids = [row["id"] for row in rows]
    checked = 0

    for start in range(0, len(ids), config.BATCH_SIZE):
        if db.remaining_quota(conn) < 5:
            logger.info("Quota knapp, Enricher pausiert")
            break

        batch = ids[start : start + config.BATCH_SIZE]
        try:
            details = youtube.fetch_videos(conn, batch)
        except youtube.QuotaExceeded:
            break
        except youtube.ApiError as exc:
            logger.warning("Enricher-Batch fehlgeschlagen: %s", exc)
            conn.executemany(
                "UPDATE videos SET duration_s = -1 WHERE id = ?",
                [(video_id,) for video_id in batch],
            )
            conn.commit()
            continue

        found = set()
        for item in details:
            found.add(item["id"])
            conn.execute(
                "UPDATE videos SET duration_s = ? WHERE id = ?",
                (youtube.duration_of(item) or -1, item["id"]),
            )

        missing = [video_id for video_id in batch if video_id not in found]
        if missing:
            conn.executemany(
                "UPDATE videos SET duration_s = -1 WHERE id = ?",
                [(video_id,) for video_id in missing],
            )

        conn.commit()
        checked += len(batch)

    if checked:
        logger.info("%d Laufzeiten nachgetragen", checked)
    return checked
