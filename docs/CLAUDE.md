# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UnseenStream is a TikTok-style interface for discovering ultra-fresh YouTube videos with 0-1 views. The project has three operational modes:

1. **Render API Mode** (optional): Serves videos with 0-1 views from a Flask backend, rotated every 1 second
2. **Live API Mode**: Real-time YouTube searches using user-provided API key
3. **Pre-fetched Mode**: Automatic fallback using locally stored videos updated hourly

## Architecture

### Three-Tier System

**Frontend (Static Web App)**
- Single-page application: `index.html`, `script.js`, `styles.css`
- YouTube IFrame API for video playback
- LocalStorage for API keys, preferences, and saved videos
- No build process required - pure HTML/CSS/JS

**Backend API (Optional - Render.com)**
- Flask server: `api/api_server.py`
- Serves random video every 1 second from pool
- Background thread rotates videos automatically
- Fetches video pool from GitHub repository hourly
- Endpoints: `/current-video`, `/stats`, `/health`

**Automation Layer (GitHub Actions)**
- Hourly video discovery: `scripts/video_discovery.py`
- Legacy camera pattern scraper: `scraper.py`
- Outputs: `videos_pool.json` (0-1 view videos), `videos.json` (fallback)
- Auto-commits updated video data

### Key Design Decisions

**Video Pool Management**
- Pool size: 1,000-10,000 videos
- Discovery window: Last 1 hour of YouTube uploads
- Max age: 48 hours (videos removed if older or exceed 1 view)
- Smart batching: 50 videos per API call to minimize quota

**API Quota Optimization**
- GitHub Actions: ~2,800 units/day (leaves 7,200 units buffer)
- 1 search = 100 units, 1 video details fetch = 1 unit
- Distributed across 24 hourly runs instead of single daily run
- Random region/language selection for content diversity

**Rotation Strategy (Render API)**
- Background thread picks random video every 1 second (86,400 videos/day)
- Thread-safe global state for current video
- Automatic pool refresh from GitHub every 60 minutes

## Development Commands

### Local Development

```bash
# Serve the static site locally
python -m http.server 8000
# Then open http://localhost:8000

# Or use any static server
npx serve .
```

### Testing Video Discovery Script

```bash
# Set API key
export YOUTUBE_API_KEY="your_api_key_here"

# Run discovery script
python scripts/video_discovery.py

# Run legacy scraper (camera patterns)
python scraper.py
```

### Testing Render API Locally

```bash
# Install dependencies
pip install -r api/requirements.txt

# Set environment variables
export GITHUB_REPO="username/UnseenStream"
export YOUTUBE_API_KEY="your_api_key_here"

# Run API server
cd api && python api_server.py
# Server runs on http://localhost:5000

# Test endpoints
curl http://localhost:5000/current-video
curl http://localhost:5000/stats
curl http://localhost:5000/health
```

### GitHub Actions Testing

```bash
# Manually trigger workflow from Actions tab
# Or simulate locally:
export YOUTUBE_API_KEY="your_api_key_here"
python scripts/video_discovery.py
```

## File Structure

```
/
├── index.html              # Main app entry point
├── script.js               # Frontend logic (Render API + YouTube API + fallback)
├── styles.css              # Styling
├── videos.json             # Fallback video database (camera patterns)
├── videos_pool.json        # Fresh 0-1 view videos pool
│
├── api/
│   ├── api_server.py       # Flask API (1-second rotation)
│   └── requirements.txt    # Flask, gunicorn, requests, flask-cors
│
├── scripts/
│   ├── video_discovery.py  # Discovers 0-1 view videos (GitHub Actions)
│   └── requirements.txt    # google-api-python-client
│
├── scraper.py              # Legacy scraper (camera patterns like DSC_1234)
├── render.yaml             # Render.com deployment config
└── .github/workflows/
    └── scrape-videos.yml   # Hourly automation (0 * * * *)
```

## Key Concepts

### Video Discovery Algorithm

**Ultra-Fresh Discovery (`video_discovery.py`)**
1. Search for videos uploaded in last 1 hour
2. Use random region/language for diversity (20 regions × 18 languages)
3. Batch check view counts (50 videos per API call)
4. Filter for 0-1 views only
5. Update existing pool: remove old/popular videos, add fresh ones
6. Safety: Never drop below 1,000 videos

**Camera Pattern Discovery (`scraper.py`)**
1. Generate random queries: DSC_1234, IMG_5678, MOV_0042, etc.
2. Search YouTube for recently uploaded videos
3. Filter by view count (0-10,000 configurable)
4. Maintain pool of ~1,000 unique videos

### Frontend State Management

```javascript
// Three operating modes
useRenderAPI       // Render.com backend enabled
API_KEY            // User's YouTube API key
usePrefetched      // Fallback to videos.json

// Video queue system
videoQueue         // Current session videos
currentIndex       // Position in queue
prefetchedVideos   // Loaded from videos.json
```

### Render API Integration

The frontend polls `/current-video` endpoint continuously. The backend's background thread ensures a new random video is available every second without client-side rotation logic.

## Common Tasks

### Adding New Video Discovery Patterns

Edit `scraper.py` line 20:
```python
PATTERNS = ['DSC', 'IMG', 'MOV', 'VID', 'GOPR', 'DJI', 'PICT']  # Add more
```

### Changing Pool Size Limits

Edit `scripts/video_discovery.py` lines 18-20:
```python
MAX_POOL_SIZE = 10000      # Maximum videos in pool
MIN_POOL_SIZE = 1000       # Safety threshold
```

### Adjusting Rotation Speed

Edit `api/api_server.py` line 82:
```python
time.sleep(1)  # Change to 0.5 for 2 videos/second, 2 for 30 videos/minute
```

### Modifying Search Window

Edit `scripts/video_discovery.py` line 23:
```python
SEARCH_WINDOW_HOURS = 1  # Change to 2 for last 2 hours
```

## API Quota Management

**Daily quota:** 10,000 units

**Current usage (GitHub Actions):**
- 1 search/hour = 100 units × 24 = 2,400 units
- View count checks = ~400 units
- Total: ~2,800 units/day

**Scaling considerations:**
- Can run up to 3 searches/hour before quota issues
- Batch API calls minimize quota (50 videos = 1 unit)
- Random sampling of existing videos reduces update costs

## Deployment

### GitHub Pages (Static Frontend)
1. Push to repository
2. Enable Pages in Settings → Pages
3. Deploy from main branch
4. Access at `https://username.github.io/UnseenStream/`

### Render.com (Optional Backend)
1. Create Web Service on Render.com
2. Connect GitHub repository
3. Set environment variable: `GITHUB_REPO=username/UnseenStream`
4. Auto-deploys from `render.yaml`
5. Set up keepalive pings (e.g., UptimeRobot) every 14 minutes

### GitHub Actions Setup
1. Add repository secret: `YOUTUBE_API_KEY`
2. Workflow runs automatically every hour
3. Commits updated `videos_pool.json` and `videos.json`

## Important Implementation Notes

### Thread Safety (Render API)
The `current_video` global variable in `api_server.py` is updated by background thread. Flask's default single-threaded mode is safe for reads. If scaling to multiple workers, add locks.

### Quota Error Handling
Both discovery scripts check for quota errors in API responses and stop gracefully:
```python
if 'quota' in str(e).lower():
    print("Quota exceeded, stopping")
    break
```

### Frontend Fallback Logic
`script.js` automatically switches to pre-fetched mode when:
- YouTube API returns quota error
- User skips API key entry
- Render API is unavailable

### Video Age Calculation
All timestamps are UTC ISO format with 'Z' suffix. Age calculations in `video_discovery.py` strip timezone for comparison:
```python
datetime.fromisoformat(video['discoveredAt'].replace('Z', ''))
```

## Configuration Files

**`render.yaml`** - Render.com deployment configuration:
- Service type: web
- Python environment
- Build: `pip install -r api/requirements.txt`
- Start: `cd api && gunicorn api_server:app`

**`.github/workflows/scrape-videos.yml`** - Hourly automation:
- Cron: `0 * * * *` (every hour at minute 0)
- Python 3.10
- Commits changes as "GitHub Actions Bot"

## Testing Checklist

When making changes:

1. **Frontend changes:**
   - Test all three modes (Render API, Live API, Pre-fetched)
   - Test swipe gestures and keyboard controls
   - Test API key save/skip flow

2. **Discovery script changes:**
   - Verify quota usage stays under budget
   - Check video pool size remains within limits
   - Ensure old/popular videos are removed

3. **API server changes:**
   - Test health endpoint returns 200
   - Verify video rotation occurs every second
   - Check pool refresh works correctly

4. **GitHub Actions changes:**
   - Test workflow with manual dispatch
   - Verify commits are pushed correctly
   - Check both JSON files are updated
