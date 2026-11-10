# Changelog

All notable changes to UnseenStream will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-10

### Changed
- **New architecture**: the hourly GitHub Actions scrape and the Render.com
  free tier are replaced by a self-hosted Docker stack on a VPS.
- **Watchlist instead of a frozen pool**: the YouTube Data API is used only
  to discover new channels; their public RSS feeds keep the pool fresh for
  free, so a quota outage no longer empties the site.
- **Adaptive polling**: channels are sorted into hot/warm/cold tiers by
  hit rate; channels that never deliver are demoted and eventually removed.
- **Frontend moved to `web/`** and served same-origin behind Caddy: no CORS,
  no cold-start countdown, no configurable API URL.
- **Storage**: one SQLite file instead of an 18.9 MB JSON rewritten hourly
  and committed to git.

### Added
- `app/` package with `discoverer`, `poller`, `api`, `seed` and a shared
  `db`/`config` layer.
- Serving filters evaluated per request: zero views only, at least two hours
  old, and longer than 180 seconds so Shorts never appear.
- `enrich` job that backfills video durations (RSS does not carry them),
  sharing the API budget with discovery.
- Quota accounting per Pacific day (`quota` table), default budget 9,700 of
  10,000 units.
- `Dockerfile`, `docker-compose.yml` with memory/CPU limits, read-only
  root filesystems and log rotation.
- Test suite (35 tests): RSS parsing, tier transitions, quota days,
  weighted selection, 503 handling.

### Removed
- `api/api_server.py`, `scripts/video_discovery.py`, `render.yaml` and the
  `scrape-videos` workflow.
- Per-second background rotation and its log volume.

## [0.1.0] - 2025-11-09

### Added
- **Ultra-Fresh Video Discovery**: New discovery system that finds videos uploaded within the last hour
- **0-1 View Filtering**: Strict filtering for truly unseen content
- **Render.com Backend**: Optional API server that rotates videos every second
- **Smart Quota Management**: Efficient batching reduces quota usage to ~2,800 units/day
- **Triple-Mode System**: Render API → YouTube API → Prefetched fallback chain
- **GitHub Actions Integration**: Hourly automated video discovery
- **10K Video Pool**: Maintains pool of 10,000 constantly refreshed videos
- **Complete Documentation**: Deployment guides, API docs, and troubleshooting

### Changed
- **Project Name**: Renamed from RandomTube to UnseenStream
- **Focus Shift**: From camera-filename videos to ultra-fresh 0-1 view content
- **Architecture**: Added backend API server for 1-second video rotation

### Technical Details
- Flask API server with 1-second background rotation
- Batch API calls (50 videos per request) for efficiency
- Smart view count checking with progressive frequency
- Videos removed when views exceed 1 or age exceeds 48 hours
- Automatic pool maintenance (never deletes if < 1,000 videos)
- Geographic and language diversity in search queries

### Files Added
- `api/api_server.py` - Backend API server with advanced logging
- `api/requirements.txt` - API dependencies
- `scripts/video_discovery.py` - Fresh video scraper
- `scripts/requirements.txt` - Scraper dependencies
- `render.yaml` - Render.com configuration
- `docs/RENDER_DEPLOYMENT.md` - Deployment guide
- `VERSION` - Version tracking
- `CHANGELOG.md` - This file

### Files Modified
- `.github/workflows/scrape-videos.yml` - Updated for new discovery script
- `script.js` - Added Render API integration
- `README.md` - Updated documentation

---

## Legacy (Pre-0.1.0)

Original RandomTube implementation with camera-filename pattern search (DSC_, IMG_, MOV_, etc.)
