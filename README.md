# UnseenStream

A TikTok-style feed of YouTube videos almost nobody has seen: 0 to 100 views,
raw and unpolished. Live at **https://unseenstream.bitmancer.net**.

## How it works

The expensive part of "find unseen videos" is not serving them, it is
discovering them: one YouTube search request costs 100 quota units, and the
free daily budget is 10,000. Storing a pool is therefore not the bottleneck —
quota is.

UnseenStream splits the two:

```
YouTube Data API  ──100 units──▶  discoverer  ──▶  channels (SQLite)
                                                        │
YouTube RSS       ──0 units────▶  poller      ◀────────┘
                                                        │
Internet Archive  ──0 units────▶  archive     ◀────────┘
                                                        │
                                                  videos (SQLite)
                                                        │
                                      api  ◀────────────┘
                                        │
                                      Caddy ──▶ browser
```

| Component | Job | Cost |
|---|---|---|
| `us-discoverer` | 4 searches per hour, enriched with `videos.list`, writes channels to the watchlist | ~9,700 units/day |
| `us-poller` | polls channel RSS feeds (views included), keeps candidates fresh | no API quota |
| `archive` | pulls fresh `mediatype:movies` items with `downloads: 0` from archive.org | no API key, polite rate limit |
| `us-api` | weighted random selection, `/current-video`, `/health`, `/stats` | none |

Both providers land in the same `videos` table; the API filters by the
`source` field sent from the frontend (`all`, `youtube`, `archive`), which
is also the toggle in the footer.

**Every video is served once.** Selection and consumption happen under one
lock, the row gets `served = 1`, and the pool query only returns
`served = 0`. A video that someone has seen anywhere on the site never
appears for anyone else.

Because RSS polling is free, a quota outage only pauses discovery — the feed
keeps working. Channels are tiered by hit rate (`hot` 10 min, `warm` 1 h,
`cold` 6 h) and dropped after five consecutive feed failures, so dead
channels clean themselves out.

## Quick start

```bash
cp .env.example .env          # add YOUTUBE_API_KEY
docker compose up -d --build
curl localhost/health         # via your reverse proxy, or:
docker exec us-api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"
```

Optionally seed the watchlist from an existing video pool:

```bash
docker compose run --rm us-discoverer python -m app.cli seed \
  --from-pool videos_pool.json --limit 20000
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `YOUTUBE_API_KEY` | — | required for discovery |
| `US_MAX_VIEWS` | `100` | discovery filter: channels that produce low-view videos are kept |
| `US_SERVE_MAX_VIEWS` | `0` | serving filter: only videos with this many views or fewer |
| `US_MIN_AGE_HOURS` | `2` | serving filter: ignore videos younger than this |
| `US_MAX_AGE_HOURS` | `48` | serving filter: ignore videos older than this |
| `US_MIN_DURATION_S` | `180` | serving filter: exclude Shorts / anything this short |
| `US_ARCHIVE_ENABLED` | `1` | enable the archive.org source |
| `US_ARCHIVE_LIMIT` | `200` | items per archive discovery run |
| `US_ARCHIVE_INTERVAL` | `600` | seconds between archive runs |
| `US_DAILY_QUOTA` | `9700` | API budget per Pacific day |
| `US_SEARCHES_PER_HOUR` | `4` | discovery pace |
| `US_HOT_INTERVAL` / `US_WARM_INTERVAL` / `US_COLD_INTERVAL` | `600` / `3600` / `21600` | poll intervals |
| `US_LOG_LEVEL` | `INFO` | logging |

Discovery and serving use different view thresholds on purpose: a channel
that produced a 40-view video is still worth tracking, but only zero-view
videos are shown.

## Endpoints

- `GET|POST /current-video` — random candidate; POST accepts
  `{"excluded_ids": [...]}` to avoid repeats.
- `GET /health` — pool size, channels, last discovery, quota used today.
- `GET /stats` — tier distribution, quota, uptime.

## Development

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows
pytest
python -m app.cli initdb
python -m app.cli poller --once --dry-run
python -m app.cli discoverer --once --dry-run
```

## Deployment notes

- Runs as three containers with `mem_limit 256m`, `cpus 0.5`, read-only root
  filesystems and log rotation, behind an existing Caddy instance.
- The frontend is served by `us-api` itself, so adding the site requires only
  a Caddy block and a config reload — no extra container, no volume changes.
- SQLite runs in WAL mode; the three containers share one `./data` directory.

## License

See `LICENSE`.
