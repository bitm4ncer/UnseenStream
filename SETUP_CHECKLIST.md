# UnseenStream Setup Checklist

Use this checklist to track your deployment progress.

---

## Phase 1: YouTube API Key ⚡

- [ ] Create Google Cloud project
- [ ] Enable YouTube Data API v3
- [ ] Create API key
- [ ] Restrict API key by HTTP referrer:
  - [ ] Add: `https://bitm4ncer.github.io/UnseenStream/*`
  - [ ] Add: `http://localhost:*`
- [ ] Restrict to YouTube Data API v3 only
- [ ] Save API key securely

**Your API Key**: `_________________________`

---

## Phase 2: GitHub Pages 🌐

- [ ] Verify `index.html` is in repository root
- [ ] Go to repository Settings → Pages
- [ ] Set Source: Deploy from branch `main` (root)
- [ ] Wait 1-2 minutes for deployment
- [ ] Visit: `https://bitm4ncer.github.io/UnseenStream/`
- [ ] Test that site loads

**Your Site URL**: `https://bitm4ncer.github.io/UnseenStream/`

---

## Phase 3: GitHub Actions (Optional but Recommended) 🤖

- [ ] Go to Settings → Secrets and variables → Actions
- [ ] Add secret: `YOUTUBE_API_KEY` with your API key
- [ ] Go to Actions tab
- [ ] Enable workflows if prompted
- [ ] Manually trigger "Scrape Fresh Videos" workflow
- [ ] Verify `videos_pool.json` was created
- [ ] Check that workflow runs successfully

**Note**: Workflow will run automatically every hour after first successful run.

---

## Phase 4: Render.com Backend (Optional) 🚀

- [ ] Sign up at [render.com](https://render.com/) with GitHub
- [ ] Create New Web Service
- [ ] Connect `bitm4ncer/UnseenStream` repository
- [ ] Configure:
  - **Name**: `unseenstream-api`
  - **Runtime**: Python 3
  - **Build**: `pip install -r api/requirements.txt`
  - **Start**: `cd api && gunicorn api_server:app`
  - **Plan**: Free
- [ ] Add environment variables:
  - `GITHUB_REPO`: `bitm4ncer/UnseenStream`
  - `POOL_REFRESH_MINUTES`: `60`
- [ ] Click "Create Web Service"
- [ ] Wait for deployment (2-5 minutes)
- [ ] Test health endpoint: `https://your-service.onrender.com/health`
- [ ] Setup keepalive (cron-job.org or UptimeRobot)
  - [ ] URL: `https://your-service.onrender.com/health`
  - [ ] Interval: Every 10 minutes
- [ ] Update `script.js` line 7 with your Render URL (or skip to let users configure)

**Your Backend URL**: `_________________________`

---

## Final Testing ✅

- [ ] Visit your GitHub Pages site
- [ ] Enter your YouTube API key when prompted
- [ ] Verify videos load and play
- [ ] Test swipe navigation (mobile or mouse drag)
- [ ] Test keyboard navigation (↑/↓ arrows)
- [ ] Save a video (heart icon)
- [ ] Check saved videos modal
- [ ] Test settings modal
- [ ] Open browser console (F12) and check for errors
- [ ] If backend deployed, verify console shows "Using Render API mode"

---

## Monitoring 📊

### Daily Checks (First Week)

- [ ] Monitor API quota: [Google Cloud Console](https://console.cloud.google.com/)
- [ ] Check GitHub Actions runs: [Actions Tab](https://github.com/bitm4ncer/UnseenStream/actions)
- [ ] Verify backend is responding (if deployed)

### Weekly Checks

- [ ] Review `videos_pool.json` size and freshness
- [ ] Check for any failed workflow runs
- [ ] Ensure backend hasn't exceeded free tier (750 hours/month)

---

## Troubleshooting Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| API quota exceeded | Wait until midnight PT; use pre-fetched videos |
| No videos loading | Check `videos.json` exists; verify API key |
| Backend sleeping | Setup keepalive service (Section 4.7) |
| GitHub Actions not running | Enable workflows in Actions tab |
| CORS errors | Verify backend URL is HTTPS |
| API key modal shows every time | Clear browser cache and re-enter key |

**Full troubleshooting**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) Section 6

---

## Configuration Summary

### What You Chose:

**Setup Type**:
- [ ] Minimal (Frontend only - GitHub Pages + manual API key)
- [ ] Recommended (Frontend + GitHub Actions - auto-updating videos)
- [ ] Full (Everything - Frontend + GitHub Actions + Render backend)

**Your Configuration**:

| Component | Status | URL/Value |
|-----------|--------|-----------|
| GitHub Pages | ⬜ | `https://bitm4ncer.github.io/UnseenStream/` |
| YouTube API Key | ⬜ | `_______________` |
| GitHub Actions | ⬜ | Enabled / Disabled |
| Render Backend | ⬜ | `_______________` |
| Keepalive Service | ⬜ | cron-job.org / UptimeRobot / None |

---

## Next Steps After Deployment

1. **Share Your Site**
   - Share the link with friends
   - Post on social media
   - Add to your portfolio

2. **Customize**
   - Modify search patterns in settings
   - Adjust view count thresholds
   - Customize UI/styling

3. **Contribute**
   - Report bugs or feature requests
   - Improve documentation
   - Share interesting videos you discover

---

## Cost Tracking

| Month | YouTube API Calls | Render Hours Used | Total Cost |
|-------|-------------------|-------------------|------------|
| Month 1 | _____ / 10,000 daily | _____ / 750 | $0 |
| Month 2 | _____ / 10,000 daily | _____ / 750 | $0 |
| Month 3 | _____ / 10,000 daily | _____ / 750 | $0 |

**Expected**: Everything should stay at **$0/month** indefinitely!

---

## Support & Resources

- 📖 **Full Guide**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- 📋 **Main README**: [README.md](README.md)
- 🚀 **Render Details**: [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md)
- 🐛 **Issues**: [GitHub Issues](https://github.com/bitm4ncer/UnseenStream/issues)

---

**Good luck with your deployment!** 🎉

If you complete all checkboxes, you'll have a fully functional video discovery platform running at zero cost!
