# Render.com Deployment Guide

Complete step-by-step guide to deploy RandomTube backend on Render.com (100% free tier).

---

## 📋 Prerequisites

- GitHub account with randomTube repository
- Render.com account (sign up at [render.com](https://render.com) - free)
- YouTube Data API v3 key (see main README)
- 10 minutes of your time

---

## 🚀 Part 1: GitHub Setup

### Step 1: Verify Your Repository

Make sure your repository has these files:
```
randomTube/
├── api/
│   ├── api_server.py
│   └── requirements.txt
├── scripts/
│   ├── video_discovery.py
│   └── requirements.txt
├── .github/workflows/
│   └── scrape-videos.yml
└── render.yaml
```

###Step 2: Update Repository (One Time)

1. **Add your GitHub username to `render.yaml`:**

   ```bash
   # Edit render.yaml
   # Find the line with GITHUB_REPO and update:
   GITHUB_REPO: YOUR_USERNAME/randomTube
   ```

2. **Commit and push:**
   ```bash
   git add render.yaml
   git commit -m "Configure Render.com deployment"
   git push
   ```

### Step 3: Verify GitHub Actions Secret

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Verify `YOUTUBE_API_KEY` secret exists
4. If not, add it now (see main README for instructions)

---

## 🎨 Part 2: Deploy to Render.com

### Step 1: Sign Up / Log In

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Sign up with GitHub (recommended) or email
3. Authorize Render to access your GitHub repositories

### Step 2: Create New Web Service

1. Click **New** → **Web Service**
2. Click **Build and deploy from a Git repository**
3. Click **Connect GitHub** (if not already connected)
4. Find and select your `randomTube` repository
5. Click **Connect**

### Step 3: Configure the Service

**Basic Settings:**
- **Name:** `randomtube-api` (or any name you prefer)
- **Region:** Oregon (US West) - recommended for free tier
- **Branch:** `main` (or `master`)
- **Root Directory:** Leave blank (uses repo root)
- **Runtime:** Python 3
- **Build Command:** `pip install -r api/requirements.txt`
- **Start Command:** `cd api && gunicorn api_server:app`

**Advanced Settings:**
- **Plan:** Free
- **Health Check Path:** `/health`
- **Auto-Deploy:** Yes (recommended)

### Step 4: Add Environment Variables

Click **Advanced** → **Add Environment Variable** and add:

| Key | Value |
|-----|-------|
| `GITHUB_REPO` | `YOUR_USERNAME/randomTube` |
| `POOL_REFRESH_MINUTES` | `60` |

**Important:** Replace `YOUR_USERNAME` with your actual GitHub username!

### Step 5: Deploy!

1. Click **Create Web Service**
2. Wait 2-5 minutes for initial build and deployment
3. Watch the logs in real-time
4. Look for: `✓ Server starting on port 10000`

### Step 6: Get Your API URL

Once deployed, you'll see:
```
https://randomtube-api.onrender.com
```

**Copy this URL!** You'll need it for the frontend.

---

## 🔧 Part 3: Configure Keepalive (Prevent Sleep)

Render free tier sleeps after 15 minutes of inactivity. We'll use cron-job.org to keep it awake.

### Option A: cron-job.org (Recommended)

1. Go to [cron-job.org](https://cron-job.org)
2. Sign up (free)
3. Click **Create cronjob**
4. Configure:
   - **Title:** RandomTube Keepalive
   - **URL:** `https://YOUR_APP.onrender.com/health`
   - **Schedule:** Every 10 minutes
   - **Timezone:** UTC
5. Save and enable

### Option B: UptimeRobot

1. Go to [uptimerobot.com](https://uptimerobot.com)
2. Sign up (free - 50 monitors)
3. Click **Add New Monitor**
4. Configure:
   - **Monitor Type:** HTTP(s)
   - **Friendly Name:** RandomTube API
   - **URL:** `https://YOUR_APP.onrender.com/health`
   - **Monitoring Interval:** 5 minutes
5. Create Monitor

---

## 🌐 Part 4: Update Frontend

### Step 1: Add API URL to Frontend

1. Open your deployed site (GitHub Pages / Netlify / etc.)
2. Open browser DevTools (F12)
3. Go to Console tab
4. Run:
   ```javascript
   localStorage.setItem('render_api_url', 'https://YOUR_APP.onrender.com');
   location.reload();
   ```

### Step 2: Verify Integration

1. Click "Next" button
2. Open Console (F12)
3. Look for: `✓ Got video from Render API:`
4. You should see a video with 0-1 views!

### Step 3: (Optional) Add UI Configuration

You can add a settings option to let users configure the Render API URL through the UI. See the main README for details.

---

## ✅ Verification Checklist

- [ ] Render.com service is deployed and running
- [ ] Service URL is: `https://YOUR_APP.onrender.com`
- [ ] `/health` endpoint returns `{"status": "healthy"}`
- [ ] `/current-video` endpoint returns a video
- [ ] `/stats` endpoint shows pool size
- [ ] Keepalive ping job is running
- [ ] GitHub Actions runs hourly
- [ ] `videos_pool.json` is being created in repository
- [ ] Frontend fetches videos from Render API
- [ ] Videos have 0-1 views

---

## 🐛 Troubleshooting

### "Service Unavailable" Error

**Cause:** Server is still starting (cold start)

**Solution:** Wait 30-60 seconds and try again

---

### "No videos in pool" Error

**Cause:** GitHub Actions hasn't run yet

**Solution:**
1. Go to GitHub → Actions tab
2. Click "Discover Fresh YouTube Videos"
3. Click "Run workflow" → "Run workflow"
4. Wait for completion (~2 minutes)
5. Verify `videos_pool.json` was created

---

### API Returns Empty/Error

**Cause:** `GITHUB_REPO` environment variable incorrect

**Solution:**
1. Go to Render dashboard
2. Click your service → Environment
3. Verify `GITHUB_REPO` = `YOUR_USERNAME/randomTube`
4. Click "Save Changes"
5. Wait for redeploy

---

### Render Service Keeps Sleeping

**Cause:** Keepalive pings not configured

**Solution:** Follow Part 3 above to set up cron-job.org or UptimeRobot

---

### GitHub Actions Quota Exceeded

**Cause:** Running too frequently or too many searches

**Solution:**
1. Check `scripts/video_discovery.py`
2. Verify `SEARCHES_PER_RUN = 1` (should be)
3. This uses ~2,800 units/day (within 10,000 limit)
4. If still exceeded, wait for quota reset (midnight PT)

---

## 📊 Monitoring

### Check API Health

```bash
curl https://YOUR_APP.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "pool_size": 1234,
  "uptime_seconds": 42.5
}
```

### Check Pool Stats

```bash
curl https://YOUR_APP.onrender.com/stats
```

Expected response:
```json
{
  "pool_size": 1234,
  "pool_last_updated": "2025-11-09T12:34:56Z",
  "videos_served": 5678,
  "server_started": "2025-11-09T12:00:00Z",
  "uptime_seconds": 2096.5,
  "github_repo": "YOUR_USERNAME/randomTube"
}
```

### Check Render.com Logs

1. Go to Render dashboard
2. Click your service
3. Click "Logs" tab
4. Watch real-time logs
5. Look for errors or warnings

### Check GitHub Actions Logs

1. Go to GitHub repository
2. Click "Actions" tab
3. Click latest workflow run
4. Expand "Run video discovery" step
5. Review output

---

## 💰 Cost Analysis

### Render.com Free Tier

- **Included:** 750 hours/month
- **Usage:** 744 hours/month (if running 24/7 with keepalive)
- **Cost:** $0

**Upgrade Path:** If you hit limits, Individual plan is $7/month for 0 sleep time.

### cron-job.org Free Tier

- **Included:** Unlimited cron jobs
- **Requests:** ~4,320/month (every 10 min)
- **Cost:** $0

### GitHub Actions Free Tier

- **Included:** 2,000 minutes/month
- **Usage:** ~60 minutes/month (hourly runs)
- **Cost:** $0

### YouTube API Quota

- **Included:** 10,000 units/day
- **Usage:** ~2,800 units/day
- **Cost:** $0

**Total Monthly Cost:** $0 🎉

---

## 🔄 Updating the API

### Auto-Deploy (Recommended)

Render.com auto-deploys on git push:

```bash
# Make changes to api/api_server.py
git add api/api_server.py
git commit -m "Update API logic"
git push

# Render.com will auto-deploy in ~2 minutes
```

### Manual Deploy

1. Go to Render dashboard
2. Click your service
3. Click "Manual Deploy" → "Deploy latest commit"

---

## 🎯 Next Steps

1. **Share Your Site:** Anyone can use it now!
2. **Monitor Quota:** Check GitHub Actions logs daily
3. **Scale Up:** Add 3 more API keys to increase to 4× speed (see main README)
4. **Customize:** Adjust view count thresholds, search parameters, etc.

---

## 📚 Related Documentation

- [Main README](../README.md) - Full project documentation
- [Render.com Docs](https://render.com/docs) - Official Render documentation
- [YouTube API Docs](https://developers.google.com/youtube/v3) - API reference

---

**Congratulations!** 🎉 Your RandomTube backend is now live and serving ultra-fresh 0-1 view videos!
