# Implementierungsplan: UnseenStream VPS-Umbau

**Spec:** `docs/superpowers/specs/2026-11-10-unseenstream-live-architektur-design.md`
**Ziel:** Lauffähiger Stack auf `unseenstream.bitmancer.net`

## Phase 1 – Anwendung

1. **Grundgerüst** `app/` anlegen: `config.py`, `db.py` (Schema, WAL,
   Helfer für Zeit/Quota).
2. **RSS-Parser** `app/rss.py` – Namespaces, Views, Datum, robust gegen
   fehlende Felder. Tests mit echten Feed-Snapshots.
3. **Tier-Logik** `app/tiers.py` – Auf-/Abstieg, Caps, Deaktivierung.
   Tests ohne Netzwerk.
4. **YouTube-Client** `app/youtube.py` – REST via `requests`, Quota-Buchung,
   `quotaExceeded`-Erkennung.
5. **Discoverer** `app/discoverer.py` – Suchrotation, Anreicherung, Upserts,
   `--dry-run`.
6. **Poller** `app/poller.py` – fällige Channels je Tier, 8 Worker,
   5 req/s, Backoff, `--once`.
7. **API** `app/api.py` – Kandidaten-Cache, gewichtete Auswahl, `/health`,
   `/stats`, `/current-video`.
8. **Seed** `app/seed.py` – alter Pool → Channel-IDs.
9. **CLI** `app/cli.py` – Rollen `api|poller|discoverer|seed`.

## Phase 2 – Frontend

10. Statische Dateien nach `web/` verschieben.
11. Cold-Start-Code, `RENDER_API_URL` und Settings-Feld entfernen;
    same-origin `POST /current-video`.
12. Player-Fehler 101/150 → automatisch weiterschalten.

## Phase 3 – Verpackung

13. `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`.
14. Container-Härtung: Limits, `read_only`, `tmpfs`, Log-Rotation,
    Healthcheck, non-root User.

## Phase 4 – Tests

15. `pytest`-Suite grün (RSS, Tiers, Auswahl, Quota). Keine Netzwerkzugriffe.

## Phase 5 – Deployment

16. Disk aufräumen (Build-Cache, ungenutzte Images) – nur nach Rückfrage.
17. `/opt/unseenstream` anlegen, Code synchronisieren, Image bauen.
18. `.env` mit `YOUTUBE_API_KEY` (vom Nutzer), `chmod 600`.
19. `docker compose up -d`, Healthchecks prüfen.
20. Caddy-Block ergänzen, `caddy validate`, `caddy reload`.
21. Ende-zu-Ende-Test über `https://unseenstream.bitmancer.net`.
22. Seed-Lauf (nach Quota-Reset) und 24-h-Beobachtung.

## Phase 6 – Aufräumen (nach Stabilität)

23. GitHub-Actions-Workflow deaktivieren/löschen, Render-Service abschalten.
24. README und CHANGELOG auf die neue Architektur umschreiben.

## Definition of Done

- Tests grün, Stack läuft, HTTPS erreichbar, `/current-video` liefert
  `views ≤ 100`, kein Container über 256 MB, andere Dienste unberührt.
