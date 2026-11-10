<p align="center">
  <img src="web/favicon.svg" alt="UnseenStream" width="96">
</p>

<p align="center">
  <strong>Watch videos nobody has seen.</strong><br>
  A swipe feed of YouTube and archive.org uploads with zero views, served once and then gone for everyone.
</p>

<p align="center">
  <a href="https://unseen.bitmancer.net"><img alt="Live: unseen.bitmancer.net" src="https://img.shields.io/badge/live-unseen.bitmancer.net-1f6feb?logo=googlechrome&logoColor=white"></a>
  <a href="https://github.com/bitm4ncer/UnseenStream/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/bitm4ncer/UnseenStream?style=social"></a>
</p>

<p align="center">
  <img alt="Only zero-view videos" src="https://img.shields.io/badge/filter-0%20views-2ea44f">
  <img alt="At least two hours old" src="https://img.shields.io/badge/age-2h%2B-6f42c1">
  <img alt="No Shorts" src="https://img.shields.io/badge/shorts-excluded-555">
  <img alt="Runs on Docker" src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white">
  <a href="https://github.com/bitm4ncer/UnseenStream/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
</p>

<p align="center">
  <a href="https://buymeacoffee.com/bitmancer"><img alt="Buy me a coffee" src="https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black"></a>
</p>

---

**[unseen.bitmancer.net](https://unseen.bitmancer.net)** shows one video at a time: zero views, at
least two hours old, longer than three minutes. As soon as a video has been served it is
consumed globally, so the next visitor gets something else. The feed mixes YouTube with
archive.org, and the footer switches between them.

## How it works

The expensive part of "find unseen videos" is not serving them, it is discovering them: one
YouTube search request costs 100 quota units and the free daily budget is 10,000. Storing a
pool is therefore not the bottleneck, quota is.

```
YouTube Data API  --100 units-->  discoverer  -->  channels (SQLite)
YouTube RSS       ---0 units--->  poller      <--
Internet Archive  ---0 units--->  archive     <--
                                      |
                                videos (SQLite)
                                      |
                        api  <--------
                          |
                        Caddy  -->  browser
```

| Component | Job | Cost |
|---|---|---|
| `us-discoverer` | 4 searches per hour, enriched with `videos.list`, writes channels to the watchlist | ~9,700 units/day |
| `us-poller` | polls channel RSS feeds (views included), keeps candidates fresh, backfills durations | no API quota |
| `archive` | pulls `mediatype:movies` items with `downloads: 0`, walks whole years backwards, extracts thumbnails with ffmpeg | no API key, polite rate limit |
| `us-api` | selection, `/current-video`, downloads, counters, static frontend | none |

YouTube and archive.org land in the same `videos` table. The API filters by the `source`
field the frontend sends (`all`, `youtube`, `archive`, or a comma-separated subset).

## What gets served

- **Zero views only.** `US_SERVE_MAX_VIEWS=0`; discovery still tracks channels up to 100 views.
- **Between 2 and 48 hours old.** Filters run at request time, so a video found at 20 minutes
  becomes eligible by itself instead of being lost.
- **Longer than 180 seconds.** RSS carries no duration, so an enricher backfills it in batches
  of 50 from `videos.list`; anything at or below the limit never appears.
- **Once, globally.** Selection and consumption happen under one lock, the row gets
  `served = 1`, and the pool query only returns `served = 0`.
- **Live view counts.** The count refreshes when a video is served and again every minute
  while it plays (throttled to one API call per video per 20 s).

## Features

- **Swipe feed** vertical swipe on mobile, arrow keys and buttons on desktop, three videos
  prefetched ahead.
- **Smooth timeline** click or drag to seek, works for both players, 3 px track with a
  draggable playhead.
- **Two sources, one feed** YouTube and archive.org, switchable in the footer.
- **Sorting** `Old` surfaces the oldest unseen uploads, `New` the freshest.
- **Uploader cooldown** the last 50 channels are remembered per browser, so the same uploader
  does not show up twice in a row.
- **Share links** copy the real source URL (`youtube.com/watch?v=…` or
  `archive.org/details/…`); `/?v=<id>` also deep-links a video inside UnseenStream.
- **Library** heart videos, reopen them later, and export everything as JSON.
- **Downloads** archive.org files directly, YouTube through the server (`yt-dlp`).
- **Unseen counter** the footer shows how many unseen videos are left, live.
- **PWA** installable, red-on-white icon, standalone display.

## Domain

`https://unseen.bitmancer.net` is the site. The old `unseenstream.bitmancer.net` host still
reaches the same container but returns `web/migrate.html`, which copies `localStorage` (saved
videos, seen list, settings) into the new origin through the URL hash and then redirects. Old
bookmarks keep working and land with their library intact.

## Downloads

archive.org items redirect straight to the public MP4. YouTube has no file URL, so the API
pulls the video with `yt-dlp` (best stream up to 720p, merged to MP4) and streams it back.

YouTube challenges datacenter IPs with "confirm you're not a bot". The API retries with the
`tv_embedded` client and, when present, uses cookies:

```
/opt/unseenstream/data/youtube-cookies.txt   # Netscape format, readable by uid 10001
```

Without cookies some videos stay blocked; the browser shows a toast instead of an error page.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET\|POST /current-video` | one candidate; POST accepts `excluded_ids`, `exclude_channels`, `source`, `sort` |
| `GET /video/<id>` | one video by id, `?refresh=1` pulls a fresh view count |
| `GET /download/<id>` | streams the video (YouTube via yt-dlp, archive.org via redirect) |
| `GET /sources` | providers this instance can serve |
| `GET /unseen-count` | size of the in-memory candidate pool, optional `?source=` |
| `GET /health` | pool size, channels, last discovery, quota used today |
| `GET /stats` | per-provider counts, tiers, quota, uptime |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `YOUTUBE_API_KEY` | — | required for discovery |
| `US_DAILY_QUOTA` | `9700` | API budget per Pacific day |
| `US_SEARCHES_PER_HOUR` | `4` | discovery pace |
| `US_MAX_VIEWS` | `100` | discovery filter: keep channels producing low-view videos |
| `US_SERVE_MAX_VIEWS` | `0` | serving filter: only videos with this many views |
| `US_MIN_AGE_HOURS` | `2` | serving filter: ignore younger videos |
| `US_MAX_AGE_HOURS` | `48` | serving filter: ignore older videos |
| `US_MIN_DURATION_S` | `180` | serving filter: exclude Shorts |
| `US_ARCHIVE_ENABLED` | `1` | enable archive.org |
| `US_ARCHIVE_LIMIT` | `200` | items per archive run |
| `US_ARCHIVE_INTERVAL` | `600` | seconds between archive runs |
| `US_ARCHIVE_VINTAGE_START` / `_END` | `2025` / `2015` | years harvested for old unseen items |
| `US_YTDLP_COOKIES` | `/data/youtube-cookies.txt` | cookie file for YouTube downloads |
| `US_HOT_INTERVAL` / `US_WARM_INTERVAL` / `US_COLD_INTERVAL` | `600` / `3600` / `21600` | poll intervals |
| `US_LOG_LEVEL` | `INFO` | logging |

Discovery and serving use different view thresholds on purpose: a channel that produced a
40-view video is still worth tracking, but only zero-view videos are shown.

## Development

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows
pytest
python -m app.cli initdb
```

Roles: `python -m app.cli {seed,discoverer,poller,enrich,bootstrap,verify,initdb}`.

## Deployment

Docker Compose on a VPS behind Caddy:

```bash
scp -r app web Dockerfile requirements.txt server:/opt/unseenstream/
ssh server "cd /opt/unseenstream && docker compose up -d --build"
```

Three containers share one SQLite volume: `us-api` (Flask, port 8000), `us-poller` and
`us-discoverer`. Caddy terminates TLS:

```
unseen.bitmancer.net {
    encode zstd gzip
    reverse_proxy us-api:8000
}
```

## License

MIT
