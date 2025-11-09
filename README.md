# UnseenStream v0.1

A TikTok-style interface for discovering truly unseen YouTube videos. Serves ultra-fresh
content with 0-1 views that most people will never see - raw, unfiltered, and completely random.

Live Demo: https://bitm4ncer.github.io/UnseenStream/

## Overview

UnseenStream operates in two modes:

1. Render API Mode (optional) - Serves videos with 0-1 views from a Flask backend,
   rotated every 1 second for truly random, never-before-seen content

2. Pre-fetched Mode (default) - Uses locally stored videos updated hourly via GitHub Actions,
   works without any backend setup

## Quick Start

### For Users (No Setup Required)

1. Open index.html in your browser
2. Start swiping through random videos

### For Developers (GitHub Actions Setup)

1. Fork this repository
2. Get a YouTube API Key from Google Cloud Console
3. Add API key as GitHub Secret: YOUTUBE_API_KEY
4. GitHub Actions will scrape videos hourly
5. Deploy to GitHub Pages or any static host

### For Power Users (Render.com Backend)

1. Complete "For Developers" setup above
2. Sign up at Render.com (free tier)
3. Deploy API server (5 minutes)
4. Configure keepalive pings for 24/7 operation
5. Get ultra-fresh 0-1 view videos rotated every second

Full deployment guide: docs/RENDER_DEPLOYMENT.md

## Features

CORE FUNCTIONALITY
- Mobile & Desktop: Swipe gestures + keyboard controls + navigation buttons
- Save Videos: Heart button to bookmark interesting finds
- Smart Fallback: Automatic switch to pre-fetched videos when needed
- Hourly Updates: GitHub Actions scrapes new videos every hour
- Zero Setup: End users don't need API keys or configuration

HOW IT WORKS
- Render API Mode (optional): Ultra-fresh 0-1 view videos, rotated every second
- Pre-fetched Mode (automatic): Local database updated hourly via GitHub Actions
- Render.com backend serves videos with 0-1 views only
- Pool of 10,000 constantly refreshed videos
- Discovers videos uploaded within last hour
- Free tier with keepalive pings

GITHUB ACTIONS AUTOMATION
- Runs every hour (distributed quota usage)
- Discovers ultra-fresh videos (uploaded in last hour)
- Maintains pool of up to 10,000 videos with 0-1 views
- Removes videos when views exceed 1 or older than 48 hours
- Uses approximately 2,800 quota units/day

## Controls

MOBILE
- Swipe Up: Next video
- Swipe Down: Previous video
- Heart Button: Save current video
- Settings: Adjust preferences
- Library: View saved videos

DESKTOP
- Keyboard: Arrow keys (up/right = next, down/left = previous), S = save
- On-screen Buttons: Click arrows on sides of video
- Mouse: Click heart to save

## Technical Details

ARCHITECTURE
- Frontend: Single-page HTML/CSS/JS application
- Backend (optional): Flask API server on Render.com
- Automation: GitHub Actions for hourly video discovery
- Storage: LocalStorage for preferences and saved videos

VIDEO DISCOVERY
- Random search queries based on camera file patterns (DSC_1234, IMG_5678, etc.)
- Filters for recently uploaded videos
- Only shows videos within configured view count range
- Queue system loads videos in batches for smooth browsing

API USAGE (GitHub Actions)
- 1 search per hour = 2,400 quota units/day
- View count checks = approximately 400 units/day
- Total: approximately 2,800 units/day (7,200 units buffer remaining)

## File Structure

```
UnseenStream/
├── index.html                   # Main application
├── script.js                    # Frontend logic
├── styles.css                   # Styling
├── videos.json                  # Pre-fetched videos database
├── videos_pool.json             # Fresh 0-1 view videos pool
│
├── api/                         # Render.com backend (optional)
│   ├── api_server.py            # Flask API server
│   └── requirements.txt         # Python dependencies
│
├── scripts/                     # GitHub Actions automation
│   ├── video_discovery.py       # Discovers 0-1 view videos
│   └── requirements.txt         # Python dependencies
│
├── .github/workflows/
│   └── scrape-videos.yml        # Hourly automation workflow
│
├── docs/
│   ├── CLAUDE.md                # Developer guide for Claude Code
│   ├── CHANGELOG.md             # Version history
│   ├── DEPLOYMENT_GUIDE.md      # Detailed deployment instructions
│   └── RENDER_DEPLOYMENT.md     # Render.com setup guide
│
└── render.yaml                  # Render.com configuration
```

## Deployment

GITHUB PAGES (Recommended for Frontend)
1. Push to repository
2. Go to Settings > Pages
3. Select source: Deploy from main branch
4. Access at: https://username.github.io/UnseenStream/

RENDER.COM (Optional Backend for 0-1 View Videos)
1. Create Web Service on Render.com
2. Connect GitHub repository
3. Set environment variable: GITHUB_REPO=username/UnseenStream
4. Auto-deploys from render.yaml
5. Set up keepalive pings (e.g., UptimeRobot) every 14 minutes

GITHUB ACTIONS (Automatic Video Discovery)
1. Add repository secret: YOUTUBE_API_KEY
2. Workflow runs automatically every hour
3. Commits updated videos_pool.json and videos.json

## Configuration

Default preferences can be modified in script.js:

```javascript
const DEFAULT_PREFERENCES = {
  maxViews: 1000,
  minViews: 0,
  dateRange: 7,
  patterns: ['DSC', 'IMG', 'MOV', 'VID']
};
```

## Development

LOCAL TESTING
```bash
# Serve static files
python -m http.server 8000
# Open http://localhost:8000

# Test video discovery script
export YOUTUBE_API_KEY="your_api_key_here"
python scripts/video_discovery.py

# Test API server locally
cd api && python api_server.py
# Server runs on http://localhost:5000
```

## Privacy & Security

- No user data collection
- No tracking or analytics
- No cookies except localStorage
- API keys stored only in browser
- Open source - all code is readable

## Getting YouTube API Key

1. Go to Google Cloud Console (console.cloud.google.com)
2. Create a new project or select existing
3. Enable "YouTube Data API v3"
4. Go to Credentials and create API Key
5. Restrict key to HTTP referrers (optional but recommended)
6. Daily quota: 10,000 units = approximately 100 searches

## License

See LICENSE file for details.

## Credits

Built as an open-source alternative to Astronaut.io and PetitTube.
Inspired by the desire to explore the "raw internet" before algorithms.
