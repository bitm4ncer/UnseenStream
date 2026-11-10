# UnseenStream – Live-Architektur auf dem VPS

**Datum:** 2026-11-10
**Status:** Freigegeben
**Zielhost:** `unseenstream.bitmancer.net` → `167.233.66.22`

## 1. Ziel

UnseenStream von der GitHub-Actions/Render-Kette auf einen eigenständigen
Docker-Stack auf `bitmancer-server` umbauen. Statt eines stündlich
eingefrorenen 50.000-Video-Pools entsteht eine Watchlist, die per
YouTube-Data-API laufend neue Channels entdeckt und diese quota-frei über
deren RSS-Feeds aktuell hält.

Erfolg heißt:

- Neue Uploads auf getrackten Channels erscheinen in ≤ 30 Minuten.
- Der Dienst läuft ohne Fremdhoster, ohne Git-Commits als Datenbank.
- Kein Quota-Ausfall macht die Seite unbrauchbar.
- Der Stack beeinflusst andere Prozesse auf dem Server nicht.

## 2. Nicht-Ziele

- Kein Scraping von YouTube-HTML oder Innertube (ToS-Verstoß).
- Keine Umgehung des API-Quotas durch mehrere Keys.
- Keine Änderungen an bestehenden Diensten auf dem Server.
- Keine Benutzerkonten, kein Tracking.

## 3. Ausgangslage und Messwerte

| Befund | Wert |
|---|---|
| Letzter Pool-Update | 2026-02-02 (9 Monate alt) |
| Workflow-Zustand | `disabled_manually`, letzte Runs `failure`/`cancelled` |
| Pool | 50.000 Videos, 18,9 MB JSON |
| Repo-Größe | ~390 MB, dominiert von stündlichen JSON-Commits |
| Tote Links im Pool | 6 von 10 zufällig geprüften Videos nicht mehr auflösbar |
| Quota-Rechnung des Altcodes | 6 Suchen/h × 100 Units = 14.400/Tag bei 10.000 Budget → überzogen |
| Scraper-Ressourcen | 0,28 s Laden, 1,74 s Schreiben, 60 MB Heap, ~3 s CPU pro Lauf |
| Server | 2 vCPU, 3,7 GB RAM, Load 0,16, 9,3 GB Disk frei (75 % belegt) |
| RSS-Test vom Server | 200 nach 0,11 s, 50 parallele Requests ohne Rate-Limit |
| RSS enthält View-Count | ja, `<media:statistics views="…"/>` pro Video |

## 4. Architektur

```
                    YouTube Data API (10.000 Units/Tag)
                              │
                 ┌────────────▼─────────────┐
                 │ us-discoverer            │  4 Suchen/h à 100 Units
                 │ search(order=date)       │  + videos.list (1 Unit/50 IDs)
                 │ → channelId, views       │
                 └────────────┬─────────────┘
                              │
                 ┌────────────▼─────────────┐
                 │ SQLite (WAL)             │
                 │ channels / videos / quota│
                 └───────┬─────────┬────────┘
                         │         │
        ┌────────────────▼──┐   ┌──▼─────────────────┐
        │ us-poller         │   │ us-api (Flask)     │
        │ RSS, 0 Units      │   │ /current-video     │
        │ Tier-Scheduling   │   │ gewichtete Auswahl │
        └───────────────────┘   └──┬─────────────────┘
                                   │
                          ┌────────▼─────────┐
                          │ Caddy            │  HTTPS + statisches Frontend
                          │ unseenstream.…   │  aus /srv/unseenstream
                          └──────────────────┘
```

### 4.1 Komponenten

| Container | Verantwortung | Limits |
|---|---|---|
| `us-discoverer` | Quota-budgetierte Suche, Anreicherung, Channel-Upsert | 256 MB, 0,5 CPU |
| `us-poller` | RSS-Polling nach Tier, Kandidaten-Upsert, Tier-Pflege | 256 MB, 0,5 CPU |
| `us-api` | Auslieferung, Health, Stats | 256 MB, 0,5 CPU |

Das Frontend läuft in keinem eigenen Container: `us-api` liefert die
statischen Dateien aus `web/` mit aus. Dadurch braucht der bestehende
Caddy-Container nur einen neuen Site-Block und ein `caddy reload` – kein
Neustart, keine Änderung an fremden Volumes.

Alle drei Rollen nutzen dasselbe Image und unterscheiden sich nur im
Startkommando. Die Kommunikation läuft ausschließlich über die SQLite-Datei
im gemeinsamen Volume – kein Message-Broker, kein Redis.

### 4.2 Warum keine Hintergrund-Rotation mehr

Der Altcode würfelt jede Sekunde ein neues Video und loggt dabei jede
Rotation (~86.000 Zeilen/Tag). Das war nötig, weil der Client ein
„aktuelles" Video abholte. Künftig wird pro Request gewürfelt; der
Hintergrundthread und die Logflut entfallen.

## 5. Datenmodell

SQLite, WAL-Modus, eine Datei unter `/data/unseenstream.db`.

```sql
CREATE TABLE channels (
  id               TEXT PRIMARY KEY,   -- UC…
  title            TEXT,
  first_seen       TEXT NOT NULL,      -- ISO-8601 UTC
  last_seen        TEXT,
  last_poll        TEXT,
  tier             TEXT NOT NULL DEFAULT 'warm',  -- hot|warm|cold
  polls            INTEGER NOT NULL DEFAULT 0,
  hits             INTEGER NOT NULL DEFAULT 0,
  hit_streak       INTEGER NOT NULL DEFAULT 0,
  polls_since_hit  INTEGER NOT NULL DEFAULT 0,
  fail_streak      INTEGER NOT NULL DEFAULT 0,
  alive            INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE videos (
  id             TEXT PRIMARY KEY,
  channel_id     TEXT,
  channel_title  TEXT,
  title          TEXT,
  thumbnail      TEXT,
  views          INTEGER NOT NULL DEFAULT 0,
  published_at   TEXT,
  discovered_at  TEXT NOT NULL,
  last_seen      TEXT NOT NULL,
  source         TEXT,                 -- search|rss|seed
  served         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE quota (
  day   TEXT PRIMARY KEY,              -- YYYY-MM-DD in America/Los_Angeles
  units INTEGER NOT NULL DEFAULT 0
);
```

Indizes: `channels(tier, last_poll)`, `videos(views, published_at)`,
`videos(channel_id)`.

## 6. Discovery (API)

Budget pro Tag: **9.700 Units** (Puffer zu 10.000).

| Posten | Rechnung |
|---|---|
| Suchen | 96 × 100 = 9.600 |
| Anreicherung | 96 × 1 = 96 |
| Reserve | 304 |

Ablauf je Lauf (4× pro Stunde):

1. Suchbegriff aus `search_terms.txt` rotieren (deterministisch gemischt,
   damit alle Begriffe gleich oft drankommen).
2. `GET /youtube/v3/search?part=snippet&type=video&order=date&publishedAfter=…&maxResults=50`.
3. IDs, die noch nicht in `videos` stehen, in 50er-Blöcken über
   `GET /youtube/v3/videos?part=snippet,statistics,contentDetails` anreichern.
4. `videos` upserten (inkl. `views`, `channel_title`), Channels upserten
   (Start-Tier `warm`).
5. Verbrauchte Units in `quota` fortschreiben.

Ist das Tagesbudget erschöpft oder antwortet die API mit
`quotaExceeded`, pausiert der Discoverer bis zum Reset um Mitternacht
Pacific. Der Poller läuft unabhängig weiter.

**Kein `part=status`:** Embeddable-Prüfung ist mit API-Key nicht
zuverlässig verfügbar; das Frontend erkennt Player-Fehler 101/150 selbst.

## 7. RSS-Polling und Tier-Logik

Quelle: `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`
(öffentlicher Syndication-Feed, kein API-Key, keine Units).

Je Eintrag werden gelesen: `yt:videoId`, `title`, `published`,
`media:group/media:thumbnail/@url`, `media:group/media:statistics/@views`.

| Tier | Cap | Takt |
|---|---|---|
| hot | 100 | 10 min |
| warm | 1.000 | 60 min |
| cold | 5.000 | 6 h |

**Übergänge** (nach jedem Poll):

- Neuer Kandidat gefunden (`views ≤ 100`, `Alter ≤ 48 h`):
  `hit_streak += 1`, `polls_since_hit = 0`; `cold → warm`, und ab
  `hit_streak ≥ 2` `warm → hot`.
- Kein Treffer: `polls_since_hit += 1`; `hot → warm` ab 6, `warm → cold`
  ab 20 leeren Polls.
- Cap überschritten: die schwächsten Channels (wenigste `hits`, ältestes
  `last_seen`) werden heruntergestuft; Cold-Überhang wird gelöscht.
- HTTP 404/410: `fail_streak += 1`; ab 3 ist der Channel `alive = 0`.
- HTTP 429/5xx: `fail_streak += 1`, nächster Versuch mit Backoff
  (`2^fail_streak` Minuten), Channel bleibt am Leben.

**Lastbegrenzung:** 8 Worker, global ≤ 5 Requests/s, Timeout 10 s.
Ein einzelner 429 bremst den gesamten Poller kurzzeitig (Circuit-Breaker).

Damit werden die 50.000 Zufalls-Channels durch eine kuratierte, sich selbst
sortierende Liste ersetzt: Wer liefert, wird öfter gefragt; wer nie liefert,
fliegt raus.

## 8. Auslieferung

`GET|POST /current-video`

- Kandidaten: `views ≤ US_SERVE_MAX_VIEWS` (Default `0`),
  `published_at` zwischen `now − 48 h` und `now − 2 h`,
  `duration_s > US_MIN_DURATION_S` (Default `180`, schließt Shorts aus).
- Die Filter greifen **beim Ausliefern**, nicht beim Sammeln: Ein Video, das
  beim Fund erst 20 Minuten alt ist, wird mit zwei Stunden automatisch
  eligible, ohne erneut gesucht werden zu müssen.
- Gewicht: `101 − views` (0 Views = 101, 100 Views = 1).
- `POST` akzeptiert `{"excluded_ids": [...]}`; bereits gesehene Videos
  werden übersprungen, solange Alternativen existieren.
- Kandidatenliste wird im Prozess gehalten und alle 20 s aus SQLite
  nachgeladen (ein Query über wenige Tausend Zeilen).
- Leere Liste → `503` mit `retry_after`.

`GET /health` → `{status, pool_size, channels, last_discovery}`.
`GET /stats` → Tier-Verteilung, Quota heute, servierte Videos.

## 9. Frontend

- `fetch('/current-video', {method:'POST', …})` – gleiche Origin, kein CORS,
  keine konfigurierbare API-URL mehr.
- Cold-Start-Erkennung, Countdown, `render_api_url` und der zugehörige
  Settings-Eintrag entfallen.
- Player-Fehler 101/150 → automatisch nächstes Video.
- LocalStorage bleibt für Favoriten und die Liste gesehener IDs.

## 10. Deployment

```
/opt/unseenstream/
├── docker-compose.yml
├── Dockerfile
├── .env                (YOUTUBE_API_KEY, chmod 600)
├── app/                (Python-Paket)
├── web/                (index.html, script.js, styles.css)
└── data/               (unseenstream.db, Bind-Mount)
```

- Image: `python:3.12-slim`, Abhängigkeiten `flask`, `gunicorn`, `requests`.
- Netzwerk: externes `web` (wie die übrigen Dienste), keine veröffentlichten
  Ports.
- Limits je Container: `mem_limit 256m`, `cpus 0.5`, `pids_limit 128`,
  `read_only: true` mit `tmpfs /tmp`, `security_opt: no-new-privileges`,
  Log-Rotation 10 MB × 3.
- Healthcheck: `GET /health` im API-Container.
- Caddy-Block in `/opt/caddy/Caddyfile` (bind-mounted), danach
  `caddy validate` und `caddy reload`.

```
unseenstream.bitmancer.net {
	encode zstd gzip
	reverse_proxy us-api:8000
}
```

Caddy bekommt das Zertifikat automatisch, sobald der DNS-Eintrag steht.

## 11. Migration

1. Stack mit leerer DB starten, Poller/API laufen sofort.
2. **Seed:** `python -m app.seed --from-pool videos_pool.json --limit 20000`
   löst Video-IDs in 50er-Blöcken zu `channelId` auf (1.000 Units, einmalig)
   und legt Channels als `cold` an. Wegen ~60 % Rot ist mit deutlich weniger
   auflösbaren IDs zu rechnen.
3. 24 h beobachten, dann Trefferquote je Tier prüfen.
4. Frontend-Cutover: GitHub Pages bleibt unverändert erreichbar, bis
   `unseenstream.bitmancer.net` stabil läuft.
5. Render-Instanz und der Actions-Workflow werden erst danach stillgelegt.

## 12. Fehlerbehandlung

| Fall | Reaktion |
|---|---|
| Quota erschöpft | Discoverer pausiert bis Reset; Poller/API unberührt |
| RSS 404/410 | Channel nach 3 Versuchen deaktiviert |
| RSS 429/5xx | Backoff, Circuit-Breaker, kein Datenverlust |
| SQLite locked | WAL + `busy_timeout=10s` |
| Leerer Kandidatenpool | 503, Frontend behält aktuelles Video |
| API-Key fehlt | Discoverer meldet das und startet nicht; Rest läuft |

## 13. Tests

- `test_rss.py` – Parsing echter Feed-Snapshots (Namespaces, Views, Datum,
  fehlende Felder).
- `test_tiers.py` – Auf-/Abstieg, Caps, Löschung nach 404-Serie.
- `test_selection.py` – Gewichtung, Ausschluss gesehener IDs, 503 bei leerem
  Pool.
- `test_quota.py` – Budgetgrenze, Tageswechsel in America/Los_Angeles.
- Alle Tests laufen ohne Netzwerk (Fixtures). Zusätzlich `--dry-run` für den
  Discoverer und `--once` für den Poller.

## 14. Risiken

| Risiko | Umgang |
|---|---|
| RSS-Rate-Limit bei mehreren Tausend Channels unklar | Backoff, Tier-Caps, Monitoring über `/stats` |
| Nur 15 Einträge pro Feed | sehr produktive Channels werden ggf. verpasst; Tier-Takt begrenzt das |
| View-Counts im RSS leicht verzögert | akzeptiert; Filter läuft zusätzlich beim Ausliefern |
| Quota-Preise könnten sich ändern | Budget ist konfigurierbar (`US_DAILY_QUOTA`) |
| Traffic ~1,6 GB/Tag im Volumen | im Panel 20 TB/Monat; unkritisch |
| Disk 75 % belegt | vor Deploy 2,2 GB Build-Cache + 2,1 GB ungenutzte Images aufräumen |

## 15. Akzeptanzkriterien

- `docker compose up -d` startet drei gesunde Container, keine
  veröffentlichten Ports.
- `https://unseenstream.bitmancer.net` liefert das Frontend über HTTPS,
  ohne CORS-Fehler und ohne Cold-Start-UI.
- `/current-video` liefert ausschließlich Videos mit `views ≤ 100`.
- Kein Container überschreitet 256 MB RAM; Load Average bleibt < 0,5.
- Nach 24 h: ≥ 95 % der gepollten Feeds antworten mit 200.
- `quota` zeigt ≤ 9.700 Units pro Tag.
