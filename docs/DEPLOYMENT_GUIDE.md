# UnseenStream Deployment Guide

Complete guide to deploying your UnseenStream application.

---

## Table of Contents

1. [Getting a YouTube API Key](#1-getting-a-youtube-api-key)
2. [Deploying Frontend to GitHub Pages](#2-deploying-frontend-to-github-pages)
3. [Setting Up GitHub Actions (Optional)](#3-setting-up-github-actions-optional)
4. [Deploying Backend to Render.com (Optional)](#4-deploying-backend-to-rendercom-optional)
5. [Configuration Summary](#5-configuration-summary)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Getting a YouTube API Key

### Step 1.1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Enter project name: `UnseenStream` (or any name)
4. Click **Create**

### Step 1.2: Enable YouTube Data API v3

1. In your project, go to **APIs & Services** → **Library**
2. Search for "YouTube Data API v3"
3. Click on it and press **Enable**

### Step 1.3: Create API Key

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **API Key**
3. Your API key will be created and displayed
4. **Copy the key** - you'll need it later

### Step 1.4: Restrict API Key (IMPORTANT for Security)

1. Click on your newly created API key to edit it
2. Under **Application restrictions**:
   - Select **HTTP referrers (web sites)**
   - Click **Add an item**
   - Add these referrers:
     - `https://yourusername.github.io/UnseenStream/*` (replace with your actual GitHub username)
     - `http://localhost:*` (for local testing)
3. Under **API restrictions**:
   - Select **Restrict key**
   - Check **YouTube Data API v3**
4. Click **Save**

### Step 1.5: Monitor Your Quota

- Daily quota: **10,000 units/day** (free tier)
- Search request: 100 units
- Video details: 1 unit
- Monitor at: [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Dashboard**

---

## 2. Deploying Frontend to GitHub Pages

### Step 2.1: Ensure Files Are Ready

Your repository should have these files in the root:
- ✅ `index.html`
- ✅ `script.js`
- ✅ `styles.css`
- ✅ `videos.json`

### Step 2.2: Enable GitHub Pages

1. Go to your repository on GitHub:
   ```
   https://github.com/bitm4ncer/UnseenStream
   ```

2. Click **Settings** (top right)

3. In the left sidebar, click **Pages**

4. Under **Source**:
   - Select **Deploy from a branch**
   - Branch: `main`
   - Folder: `/ (root)`

5. Click **Save**

6. Wait 1-2 minutes for deployment

7. Your site will be live at:
   ```
   https://bitm4ncer.github.io/UnseenStream/
   ```

### Step 2.3: Update API Key Restrictions

1. Go back to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** → **Credentials**
3. Edit your API key
4. Update the HTTP referrer to match your GitHub Pages URL:
   ```
   https://bitm4ncer.github.io/UnseenStream/*
   ```
5. Save

### Step 2.4: Test Your Deployment

1. Visit: `https://bitm4ncer.github.io/UnseenStream/`
2. You should see a modal asking for your YouTube API key
3. Enter your API key and click **Save & Start**
4. The app should load and start playing videos

---

## 3. Setting Up GitHub Actions (Optional)

GitHub Actions will automatically scrape fresh videos every hour and commit them to your repository.

### Step 3.1: Add Repository Secret

1. Go to your repository on GitHub:
   ```
   https://github.com/bitm4ncer/UnseenStream/settings/secrets/actions
   ```

2. Click **New repository secret**

3. Name: `YOUTUBE_API_KEY`

4. Value: Paste your YouTube API key

5. Click **Add secret**

### Step 3.2: Enable Workflow

The workflow file already exists at `.github/workflows/scrape-videos.yml`

To enable it:

1. Go to your repository → **Actions** tab
2. If prompted to enable workflows, click **I understand my workflows, go ahead and enable them**
3. You should see "Scrape Fresh Videos" workflow listed

### Step 3.3: Test Manual Run

1. Click on **Scrape Fresh Videos** workflow
2. Click **Run workflow** → **Run workflow**
3. Wait for the job to complete (2-5 minutes)
4. Check if `videos_pool.json` was created/updated in your repository

### Step 3.4: Automatic Runs

- The workflow runs **every hour** automatically
- It creates/updates `videos_pool.json` with fresh 0-1 view videos
- Videos are automatically committed to your repository
- The backend API (if deployed) will fetch from this file

### Step 3.5: Monitor Workflow

- View runs: `https://github.com/bitm4ncer/UnseenStream/actions`
- Check logs for errors or API quota issues
- Expected API usage: ~2,800 units/day (well under 10,000 limit)

---

## 4. Deploying Backend to Render.com (Optional)

The backend provides enhanced features like real-time video rotation and centralized video pool management.

### Step 4.1: Create Render Account

1. Go to [render.com](https://render.com/)
2. Click **Get Started for Free**
3. Sign up with GitHub (easiest option)
4. **No credit card required** for free tier

### Step 4.2: Create New Web Service

1. From Render dashboard, click **New** → **Web Service**

2. Click **Connect** next to your GitHub account (if not connected)

3. Find and select `bitm4ncer/UnseenStream` repository

4. Click **Connect**

### Step 4.3: Configure Web Service

Fill in these settings:

- **Name**: `unseenstream-api` (or any name you prefer)
- **Region**: Choose closest to you (e.g., Oregon)
- **Branch**: `main`
- **Root Directory**: Leave empty
- **Runtime**: `Python 3`
- **Build Command**:
  ```bash
  pip install -r api/requirements.txt
  ```
- **Start Command**:
  ```bash
  cd api && gunicorn api_server:app
  ```
- **Plan**: **Free**

### Step 4.4: Add Environment Variables

Click **Advanced** → **Add Environment Variable** and add these:

| Key | Value |
|-----|-------|
| `GITHUB_REPO` | `bitm4ncer/UnseenStream` |
| `POOL_REFRESH_MINUTES` | `60` |

### Step 4.5: Deploy

1. Click **Create Web Service**
2. Render will start building and deploying (takes 2-5 minutes)
3. Wait for status to show "Live"
4. Copy your service URL (e.g., `https://unseenstream-api.onrender.com`)

### Step 4.6: Test Backend

Visit these endpoints in your browser:

- **Health Check**:
  ```
  https://unseenstream-api.onrender.com/health
  ```
  Should return: `{"status": "healthy"}`

- **Stats**:
  ```
  https://unseenstream-api.onrender.com/stats
  ```
  Should return video pool statistics

- **Current Video**:
  ```
  https://unseenstream-api.onrender.com/current-video
  ```
  Should return a random video from the pool

### Step 4.7: Keep Backend Alive (Free Tier Limitation)

Free tier on Render.com sleeps after 15 minutes of inactivity. To keep it alive:

**Option A: Use cron-job.org**

1. Go to [cron-job.org](https://cron-job.org/) and create free account
2. Create new cron job:
   - Title: `UnseenStream Keepalive`
   - URL: `https://unseenstream-api.onrender.com/health`
   - Schedule: Every 10 minutes
   - Enable

**Option B: Use UptimeRobot**

1. Go to [uptimerobot.com](https://uptimerobot.com/) and create free account
2. Add New Monitor:
   - Monitor Type: HTTP(s)
   - Friendly Name: `UnseenStream API`
   - URL: `https://unseenstream-api.onrender.com/health`
   - Monitoring Interval: 5 minutes
   - Create Monitor

### Step 4.8: Configure Frontend to Use Backend

**Option 1: Update script.js (Recommended)**

Edit [script.js](script.js) line 7:

```javascript
const RENDER_API_URL = localStorage.getItem('render_api_url') || 'https://unseenstream-api.onrender.com';
```

Replace `https://unseenstream-api.onrender.com` with your actual Render URL.

**Option 2: Let Users Configure**

Users can set the backend URL in the app settings (Settings → Advanced → Render API URL).

### Step 4.9: Verify Full Stack

1. Visit your frontend: `https://bitm4ncer.github.io/UnseenStream/`
2. Open browser console (F12)
3. Look for: `Using Render API mode`
4. Videos should now be served from your backend
5. Videos will rotate every 1 second automatically

---

## 5. Configuration Summary

### Minimal Setup (Frontend Only)

**Cost**: $0/month
**Required**:
- ✅ YouTube API key
- ✅ GitHub Pages enabled
- ✅ `videos.json` in repository

**Steps**:
1. Get YouTube API key → Section 1
2. Enable GitHub Pages → Section 2
3. Enter API key when prompted

**Features**:
- Browse pre-fetched videos from `videos.json`
- Swipe navigation
- Save videos
- Manual refresh

---

### Recommended Setup (Frontend + GitHub Actions)

**Cost**: $0/month
**Required**:
- ✅ YouTube API key (as repository secret)
- ✅ GitHub Pages enabled
- ✅ GitHub Actions enabled

**Steps**:
1. Get YouTube API key → Section 1
2. Enable GitHub Pages → Section 2
3. Setup GitHub Actions → Section 3

**Features**:
- All minimal features
- Auto-updated video pool every hour
- Fresh 0-1 view videos
- No manual scraping needed

---

### Full Setup (Everything)

**Cost**: $0/month
**Required**:
- ✅ YouTube API key (as repository secret)
- ✅ GitHub Pages enabled
- ✅ GitHub Actions enabled
- ✅ Render.com account
- ✅ Keepalive service (cron-job.org or UptimeRobot)

**Steps**:
1. Get YouTube API key → Section 1
2. Enable GitHub Pages → Section 2
3. Setup GitHub Actions → Section 3
4. Deploy to Render.com → Section 4

**Features**:
- All recommended features
- Real-time video rotation (1 second intervals)
- Centralized video pool (up to 10,000 videos)
- Better quota management
- Enhanced discovery algorithm

---

## 6. Troubleshooting

### Frontend Issues

**Problem**: Modal asking for API key on every visit

**Solution**: Check browser console for localStorage errors. Clear site data and re-enter key.

---

**Problem**: "API quota exceeded" error

**Solution**:
- Check quota at [Google Cloud Console](https://console.cloud.google.com/)
- Wait until quota resets (midnight Pacific Time)
- Use GitHub Actions + Render.com backend to reduce direct API calls
- Fallback to pre-fetched videos automatically happens

---

**Problem**: No videos loading

**Solution**:
1. Check if `videos.json` exists in repository
2. Verify API key is correct and not restricted incorrectly
3. Check browser console (F12) for errors
4. Ensure YouTube Data API v3 is enabled in Google Cloud

---

### GitHub Actions Issues

**Problem**: Workflow not running automatically

**Solution**:
- Go to repository → Actions tab
- Check if workflows are enabled
- Verify `YOUTUBE_API_KEY` secret is set correctly
- Check latest run logs for errors

---

**Problem**: "Permission denied" when pushing

**Solution**:
- GitHub Actions needs write permissions
- Go to Settings → Actions → General
- Under "Workflow permissions", select "Read and write permissions"
- Save

---

**Problem**: API quota exceeded in Actions

**Solution**:
- Reduce scraping frequency (edit `.github/workflows/scrape-videos.yml`)
- Change cron schedule from `'0 * * * *'` (hourly) to `'0 */2 * * *'` (every 2 hours)

---

### Render.com Backend Issues

**Problem**: Backend keeps sleeping

**Solution**:
- Setup keepalive service (cron-job.org or UptimeRobot) - Section 4.7
- Ping interval must be ≤ 14 minutes for free tier

---

**Problem**: "No videos in pool" error

**Solution**:
1. Ensure GitHub Actions has run and created `videos_pool.json`
2. Check `GITHUB_REPO` environment variable is set correctly
3. Verify repository is public (or provide GitHub token)
4. Check Render logs for detailed error

---

**Problem**: Backend responds but frontend doesn't use it

**Solution**:
1. Check `RENDER_API_URL` in [script.js](script.js) line 7
2. Verify CORS headers in backend (should be enabled)
3. Check browser console for CORS errors
4. Ensure backend URL is HTTPS

---

### API Key Security

**Problem**: Worried about exposed API key

**Solution**:
1. API key restriction by HTTP referrer prevents abuse ✅
2. Only your domain can use the key
3. Monitor quota daily in Google Cloud Console
4. If compromised: regenerate key immediately
5. Update restrictions after regenerating

---

## Next Steps

After deployment:

1. ✅ **Test thoroughly** - Try all features on live site
2. ✅ **Monitor quota** - Check daily API usage
3. ✅ **Share your site** - Let others discover unseen content!
4. ✅ **Customize** - Modify patterns, view thresholds, UI
5. ✅ **Star the repo** - Help others find this project

---

## Cost Breakdown

| Service | Free Tier | Your Cost |
|---------|-----------|-----------|
| GitHub Pages | Unlimited (public repos) | **$0/month** |
| GitHub Actions | 2,000 minutes/month | **$0/month** |
| YouTube API | 10,000 units/day | **$0/month** |
| Render.com | 750 hours/month | **$0/month** |
| Keepalive (cron-job.org) | Unlimited | **$0/month** |
| **TOTAL** | | **$0/month** |

---

## Support

- **Issues**: [GitHub Issues](https://github.com/bitm4ncer/UnseenStream/issues)
- **Discussions**: [GitHub Discussions](https://github.com/bitm4ncer/UnseenStream/discussions)
- **Documentation**: [README.md](README.md)
- **Render Deployment Details**: [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md)

---

**Congratulations!** 🎉 Your UnseenStream app is now deployed and discovering the internet's hidden gems!
