"""Einstiegspunkt fuer alle Rollen: api, poller, discoverer, seed, initdb, stats."""

import argparse
import logging
import os
import sys

from . import config, db


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("US_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()

    parser = argparse.ArgumentParser(prog="unseenstream")
    sub = parser.add_subparsers(dest="role", required=True)

    api_parser = sub.add_parser("api", help="HTTP-API starten (Entwicklung)")
    api_parser.add_argument("--port", type=int, default=8000)
    api_parser.add_argument("--host", default="0.0.0.0")

    poller_parser = sub.add_parser("poller", help="RSS-Feeds pollen")
    poller_parser.add_argument("--once", action="store_true")
    poller_parser.add_argument("--dry-run", action="store_true")

    discover_parser = sub.add_parser("discoverer", help="YouTube-Suche ausfuehren")
    discover_parser.add_argument("--once", action="store_true")
    discover_parser.add_argument("--dry-run", action="store_true")

    seed_parser = sub.add_parser("seed", help="Alten Pool in Channels aufloesen")
    seed_parser.add_argument("--from-pool", required=True)
    seed_parser.add_argument("--limit", type=int, default=5000)
    seed_parser.add_argument("--dry-run", action="store_true")

    sub.add_parser("initdb", help="Datenbank anlegen")

    stats_parser = sub.add_parser("stats", help="Kennzahlen ausgeben")
    stats_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.role == "api":
        from . import api

        api.app.run(host=args.host, port=args.port, debug=False)
        return 0

    if args.role == "poller":
        from . import poller

        poller.run(once=args.once, dry_run=args.dry_run)
        return 0

    if args.role == "discoverer":
        from . import discoverer

        discoverer.run(dry_run=args.dry_run, once=args.once)
        return 0

    if args.role == "seed":
        from . import seed

        seed.run(args.from_pool, limit=args.limit, dry_run=args.dry_run)
        return 0

    if args.role == "initdb":
        conn = db.connect()
        conn.execute("SELECT 1")
        print(f"Datenbank bereit: {config.DB_PATH}")
        return 0

    if args.role == "stats":
        import json

        conn = db.connect()
        tiers = {
            row["tier"]: row["count"]
            for row in conn.execute(
                "SELECT tier, COUNT(*) AS count FROM channels "
                "WHERE alive = 1 GROUP BY tier"
            )
        }
        payload = {
            "db": config.DB_PATH,
            "videos_total": conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
            "videos_pool": conn.execute(
                "SELECT COUNT(*) FROM videos WHERE views <= ?", (config.MAX_VIEWS,)
            ).fetchone()[0],
            "channels_by_tier": tiers,
            "channels_dead": conn.execute(
                "SELECT COUNT(*) FROM channels WHERE alive = 0"
            ).fetchone()[0],
            "quota_today": db.spent_today(conn),
            "quota_budget": config.DAILY_QUOTA,
            "last_discovery": db.get_meta(conn, "last_discovery"),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key:18} {value}")
        return 0

    parser.error("unbekannte Rolle")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
