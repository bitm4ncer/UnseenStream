# UnseenStream v0.1

A TikTok-style interface for discovering truly unseen YouTube videos. Serves ultra-fresh
content with 0-1 views that most people will never see - raw, unfiltered, and completely random.

Live Demo: https://bitm4ncer.github.io/UnseenStream/

## Overview

UnseenStream streams videos with 0-100 views from a Flask backend API hosted on Render.com,
with videos rotated every 1 second for truly random, never-before-seen content.

The backend maintains a pool of up to 50,000 ultra-fresh videos (uploaded within the last 6 hours),
automatically refreshed hourly via GitHub Actions.

## Quick Start

### Deployment (Required)

1. Fork this repository
2. Get a YouTube API Key from Google Cloud Console
3. Add API key as GitHub Secret: YOUTUBE_API_KEY
4. Sign up at Render.com (free tier)
5. Deploy API server using render.yaml (auto-deployment)
6. Deploy frontend to GitHub Pages
7. Configure Render API URL in frontend settings
8. Set up keepalive pings (e.g., UptimeRobot) every 14 minutes for 24/7 operation

Full deployment guide: docs/RENDER_DEPLOYMENT.md

### Cold Start Behavior

When the Render.com free tier server sleeps after 15 minutes of inactivity:
- Frontend automatically detects cold start
- Shows countdown timer and progress bar (up to 90 seconds)
- Begins serving videos once server is ready

## Features

CORE FUNCTIONALITY
- Mobile & Desktop: Swipe gestures + keyboard controls + navigation buttons
- Save Videos: Heart button to bookmark interesting finds
- Cold Start Detection: Automatic server wake-up with visual feedback
- Hourly Updates: GitHub Actions scrapes new videos every hour
- Ultra-Fresh Content: Videos with 0-100 views, weighted toward 0 views
- No Duplicates: Tracks viewed videos to ensure fresh content per user

HOW IT WORKS
- Render.com backend serves videos with 0-100 views
- Weighted random selection: 0 views = highest priority, 100 views = lowest
- Pool of up to 50,000 constantly refreshed videos
- Discovers videos uploaded within last hour
- 1-second rotation for maximum randomness
- Duplicate prevention via LocalStorage tracking
- Free tier with keepalive pings for 24/7 operation

GITHUB ACTIONS AUTOMATION
- Runs every hour (distributed quota usage)
- Discovers ultra-fresh videos (uploaded in last 6 hours)
- Maintains pool of up to 50,000 videos with 0-100 views
- Removes videos when views exceed 100
- Uses approximately 6,400 quota units/day (64% of free quota)

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
- Frontend: Single-page HTML/CSS/JS application (GitHub Pages)
- Backend: Flask API server on Render.com (required)
- Automation: GitHub Actions for hourly video discovery
- Storage: LocalStorage for preferences and saved videos

VIDEO DISCOVERY & SELECTION
- Random search queries with geographic and language diversity
- Filters for videos uploaded within last 6 hours
- Only serves videos with 0-100 views
- Weighted random selection algorithm:
  * 0 views = weight 101 (highest priority)
  * 100 views = weight 1 (lowest priority)
  * Maintains randomness while favoring fresher content
- Duplicate prevention: tracks up to 1000 viewed videos per user
- Backend rotates current video every 1 second
- Frontend fetches new video on each swipe
- Discovers ~270 new videos per hour

API USAGE (GitHub Actions)
- 6 searches per hour = 6,000 quota units/day
- View count checks = approximately 400 units/day
- Total: approximately 6,400 units/day (3,600 units buffer remaining)

## File Structure

```
UnseenStream/
├── index.html                   # Main application
├── script.js                    # Frontend logic with cold-start detection
├── styles.css                   # Styling
├── videos_pool.json             # Fresh 0-100 view videos pool (for Render API)
│
├── api/                         # Render.com backend (required)
│   ├── api_server.py            # Flask API server with advanced logging
│   └── requirements.txt         # Python dependencies
│
├── scripts/                     # GitHub Actions automation
│   ├── video_discovery.py       # Discovers 0-100 view videos (6 searches/hour)
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

GITHUB PAGES (Frontend Deployment)
1. Push to repository
2. Go to Settings > Pages
3. Select source: Deploy from main branch
4. Access at: https://username.github.io/UnseenStream/
5. Configure Render API URL in settings (https://your-app.onrender.com)

RENDER.COM (Backend Deployment - Required)
1. Create Web Service on Render.com
2. Connect GitHub repository
3. Set environment variable: GITHUB_REPO=username/UnseenStream
4. Auto-deploys from render.yaml
5. Set up keepalive pings (e.g., UptimeRobot) every 14 minutes for 24/7 operation

GITHUB ACTIONS (Automatic Video Discovery)
1. Add repository secret: YOUTUBE_API_KEY
2. Workflow runs automatically every hour
3. Commits updated videos_pool.json to repository

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
