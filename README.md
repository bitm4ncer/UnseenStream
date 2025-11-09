# UnseenStream v0.1

A TikTok-style interface for discovering truly unseen YouTube videos. Serves ultra-fresh content with 0-1 views that most people will never see - raw, unfiltered, and completely random.

## 🎯 New Features

### Ultra-Fresh Video Discovery (Render.com Backend)
Now with **0-1 view videos** served every second! Deploy the optional Render.com backend to get truly random, never-before-seen YouTube content. Videos are discovered hourly and rotated every second.

### Automated Video Scraping (GitHub Actions)
GitHub Actions automation distributes API quota throughout the day, ensuring 24/7 availability even when quota limits are reached!

## 🚀 Quick Start

### For Users (No Setup Required)
1. Open `index.html` in your browser
2. Start swiping! (Uses pre-fetched videos)

### For Developers (GitHub Actions Only)
1. Fork this repository
2. Get a YouTube API Key (see below)
3. Add API key as GitHub Secret: `YOUTUBE_API_KEY`
4. GitHub Actions will scrape videos hourly
5. Deploy to GitHub Pages or any static host

### For Power Users (Render.com Backend - 0-1 View Videos!)
1. Complete "For Developers" setup above
2. Sign up at [Render.com](https://render.com) (free)
3. Deploy API server (5 minutes)
4. Configure keepalive pings
5. Get ultra-fresh 0-1 view videos!

**Full guide:** [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md)

## 📹 Getting Your YouTube API Key (FREE)

### Step-by-Step:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Click "Enable APIs and Services"
4. Search for "YouTube Data API v3"
5. Click "Enable"
6. Go to "Credentials" in the left menu
7. Click "Create Credentials" → "API Key"
8. Copy your API key

### Optional but Recommended - Restrict Your API Key:

1. Click on your API key to edit it
2. Under "Application restrictions", select "HTTP referrers"
3. Add your domain (e.g., `yourdomain.com/*` or `localhost/*` for testing)
4. Under "API restrictions", select "Restrict key"
5. Choose "YouTube Data API v3"
6. Save

**Daily Quota:** 10,000 units/day = ~100 searches (plenty for personal use!)

## ✨ Features

### Core Functionality
- 📱 **Mobile & Desktop**: Swipe gestures + keyboard controls + navigation buttons
- ❤️ **Save Videos**: Heart button to bookmark interesting finds
- ⚙️ **Customizable Filters**: View count, date range, filename patterns
- 💾 **Smart Fallback**: Automatic switch to pre-fetched videos when API quota is exhausted
- 🔄 **Hourly Updates**: GitHub Actions scrapes new videos every hour
- 🎯 **Zero Quota Cost**: End users don't consume API quota (uses pre-fetched database)

### How It Works

**Triple-Mode System:**
1. **Render API Mode** (optional) - Ultra-fresh 0-1 view videos, rotated every second
2. **Live API Mode** (default) - Real-time YouTube searches for fresh content
3. **Pre-fetched Mode** (automatic fallback) - Local database updated hourly via GitHub Actions

**Render.com Backend (Optional):**
- Serves videos with 0-1 views only
- New random video every 1 second (86,400 videos/day shown)
- Pool of 10,000 constantly refreshed videos
- Discovers videos uploaded within last hour
- Free tier with keepalive pings
- See [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md)

**GitHub Actions Automation:**
- Runs every hour (distributed quota usage)
- Discovers ultra-fresh videos (uploaded in last hour)
- Maintains pool of up to 10,000 videos with 0-1 views
- Removes videos when views exceed 1 or older than 48 hours
- Uses ~2,800 quota units/day (leaves 7,200 for scaling)
- Creates `videos_pool.json` for Render API
- Also maintains `videos.json` for fallback mode

## 🎮 How to Use

1. **First Time Setup**: Enter your API key when prompted
2. **Swipe Up**: Get next random video
3. **Swipe Down**: Go back to previous video
4. **Heart Button (♡)**: Save current video
5. **Settings (⚙️)**: Adjust preferences
6. **Saved (📚)**: View all saved videos

### Desktop Controls
- **Keyboard**: `↑`/`→` (next), `↓`/`←` (previous), `S` (save)
- **On-screen Buttons**: Click ← → arrows on sides of video
- **Mouse**: Click heart to save

## 🔧 Technical Details

### What Happens Under the Hood:

1. **Random Search**: Generates queries like "DSC_1234", "IMG_5678"
2. **API Call**: Searches YouTube for recently uploaded videos
3. **Filtering**: Only shows videos within your view count range
4. **Queue System**: Loads 50 videos at a time for smooth swiping
5. **Smart Fetching**: Auto-loads more when you're running low

### Data Storage:
- **API Key**: Stored in localStorage
- **Preferences**: Stored in localStorage
- **Saved Videos**: Stored in localStorage (max ~10MB)
- **No server needed**: Everything runs in your browser

### API Usage:
- 1 search = 100 quota units
- 1 video details fetch = 1 quota unit
- Each batch uses ~150 units
- You can do ~65 searches per day

## 🛠️ Customization

### Want to modify the search patterns?

Open the HTML file and find this section:

```javascript
const DEFAULT_PREFERENCES = {
  maxViews: 1000,
  minViews: 0,
  dateRange: 7,
  patterns: ['DSC', 'IMG', 'MOV', 'VID']
};
```

### Want different camera patterns?

Add more patterns in the settings modal section:

```html
<label class="checkbox-item">
  <input type="checkbox" value="PICT"> PICT
</label>
```

## 🐛 Troubleshooting

### "Error loading videos. Check your API key."
- Make sure your API key is correct
- Check that YouTube Data API v3 is enabled in Google Cloud Console
- Verify you haven't exceeded your daily quota

### Videos won't play
- Some videos may be region-restricted
- The video might have been deleted since upload
- Try swiping to the next video

### App seems slow
- The app fetches 50 videos at a time
- First load might take a few seconds
- Subsequent videos load from the queue (instant)

### No videos found
- Try adjusting your max view count (increase it)
- Change the date range to last 30 or 90 days
- Enable more title patterns in settings

## 🚀 Setup Guide for GitHub Actions

### Prerequisites
- GitHub account
- YouTube Data API key

### Step 1: Fork Repository
```bash
git clone https://github.com/YOUR_USERNAME/randomTube.git
cd randomTube
```

### Step 2: Configure API Key in GitHub
1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `YOUTUBE_API_KEY`
5. Value: Your YouTube API key
6. Click **Add secret**

### Step 3: Enable GitHub Actions
1. Go to the **Actions** tab
2. Enable workflows if prompted
3. The scraper will run automatically every hour

### Step 4: Manual Test (Optional)
1. Go to **Actions** → **Scrape YouTube Videos**
2. Click **Run workflow** → **Run workflow**
3. Wait for completion
4. Check that `videos.json` was updated

### Step 5: Deploy
Choose one of these options:

#### Option A: GitHub Pages (Recommended)
1. Go to **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **root**
4. Save
5. Visit `https://YOUR_USERNAME.github.io/randomTube`

#### Option B: Netlify
1. Connect your GitHub repo to Netlify
2. Build settings: None needed (static site)
3. Publish directory: `/`
4. Deploy!

#### Option C: Vercel
1. Import your GitHub repo
2. Framework: **Other**
3. Root directory: `./`
4. Deploy!

### Local Development
```bash
# Install Python dependencies
pip install google-api-python-client

# Set environment variable
export YOUTUBE_API_KEY="your_api_key_here"

# Run scraper manually
python scraper.py

# Open in browser
open index.html
```

## 🔒 Privacy & Security

- **Your API key** is stored only in your browser
- **No data** is sent to any server except YouTube
- **No tracking** or analytics
- **No cookies** except localStorage
- **Open source** - you can read all the code

## 📊 File Structure

```
UnseenStream/
├── index.html                       # Main app (single-file, works standalone)
├── script.js                        # Frontend logic with Render API integration
├── styles.css                       # Styling
│
├── api/                            # Render.com backend (optional)
│   ├── api_server.py               # Flask API server (1-second rotation)
│   └── requirements.txt            # Python dependencies
│
├── scripts/                        # GitHub Actions scripts
│   ├── video_discovery.py          # Discovers 0-1 view videos
│   └── requirements.txt            # Python dependencies
│
├── scraper.py                      # Legacy scraper (camera patterns)
├── videos.json                     # Fallback videos database
├── videos_pool.json                # Fresh 0-1 view videos pool
│
├── .github/workflows/
│   └── scrape-videos.yml           # Hourly automation workflow
│
├── docs/
│   └── RENDER_DEPLOYMENT.md        # Render.com deployment guide
│
├── render.yaml                     # Render.com configuration
└── README.md                       # This file
```

## 💡 Pro Tips

1. **Lower view counts** = More weird/interesting content
2. **Recent uploads only** (7 days) = More unedited raw footage
3. **Save liberally** - You can always remove videos later
4. **Try different patterns** - Each one finds different content
5. **Desktop keyboard** - Use arrow keys for rapid browsing
6. **Let GitHub Actions run** - Wait a few hours after setup to build video database

## 🎯 Future Ideas (Not Implemented Yet)

Want to add these features yourself?
- Export saved videos as JSON
- Import saved videos from file
- Share video discoveries
- Dark/light theme toggle
- Video quality selector
- Auto-play next video
- Random playlist generator

## 📊 How the Randomness Works

The app doesn't use YouTube's recommendation algorithm at all!

Instead it:
1. Generates random camera filename patterns
2. Searches for videos with those exact titles
3. Filters by recent upload date
4. Filters by low view count
5. Shuffles results

This finds videos that:
- Were uploaded directly from cameras
- Haven't been edited (still have default names)
- Barely anyone has seen
- Are completely raw/authentic

## ❓ FAQ

**Q: Is this legal?**
A: Yes! You're using YouTube's official API.

**Q: Will I run out of quota?**
A: Unlikely for personal use. ~100 searches/day is plenty. With Render backend, it uses only ~2,800 units/day.

**Q: What's the difference between Render API and regular mode?**
A: Render API serves only 0-1 view videos (truly never-seen content), rotated every second. Regular mode searches for low-view videos with camera filenames.

**Q: Do I need the Render.com backend?**
A: No, it's optional! The app works great without it. Render backend is for power users who want the freshest possible content.

**Q: Is Render.com really free?**
A: Yes! The free tier includes 750 hours/month, which covers 24/7 operation with keepalive pings. No credit card required.

**Q: How many videos with 0-1 views are there on YouTube?**
A: Thousands are uploaded every hour! The pool stays at 10,000 videos constantly refreshed.

**Q: Can I use this for commercial projects?**
A: Check YouTube's API Terms of Service.

**Q: Why do some videos have no sound?**
A: Many camera uploads are muted or have wind noise only.

**Q: Can I download the videos?**
A: This app only views videos. Use YouTube's download feature.

**Q: Does this work offline?**
A: No, it needs internet to fetch videos from YouTube.

## 🙏 Credits

Built as an open-source alternative to Astronaut.io and PetitTube.

Inspired by the desire to explore the "raw internet" before algorithms.

---

**Enjoy discovering the hidden corners of YouTube!** 🎥✨