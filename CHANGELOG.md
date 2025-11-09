# Changelog

All notable changes to UnseenStream will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- `api/api_server.py` - Backend API server
- `api/requirements.txt` - API dependencies
- `scripts/video_discovery.py` - Fresh video scraper
- `scripts/requirements.txt` - Scraper dependencies
- `render.yaml` - Render.com configuration
- `.env.example` - Environment variables template
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
