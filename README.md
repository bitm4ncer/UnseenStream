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
| `us-api` | weighted random selection, `/current-video`, `/health`, `/stats` | none |

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
| `US_MAX_VIEWS` | `100` | upper view limit |
| `US_MAX_AGE_HOURS` | `48` | candidate age window |
| `US_DAILY_QUOTA` | `9700` | API budget per Pacific day |
| `US_SEARCHES_PER_HOUR` | `4` | discovery pace |
| `US_HOT_INTERVAL` / `US_WARM_INTERVAL` / `US_COLD_INTERVAL` | `600` / `3600` / `21600` | poll intervals |
| `US_LOG_LEVEL` | `INFO` | logging |

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
