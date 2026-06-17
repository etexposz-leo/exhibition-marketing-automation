# Render Deployment Guide

## Quick Deploy from GitHub

### Step 1: Go to Render Dashboard
1. Visit [dashboard.render.com](https://dashboard.render.com)
2. Log in with your GitHub account

### Step 2: Create New Web Service
1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub account if not already connected
3. Find and select the repository: `etexposz-leo/exhibition-marketing-automation`

### Step 3: Configure the Service

| Setting | Value |
|---------|-------|
| **Name** | `exhibition-marketing-automation` |
| **Region** | Oregon (or your preferred region) |
| **Branch** | `main` |
| **Runtime** | `Python 3.11` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

### Step 4: Set Environment Variables

Click **"Advanced"** → **"Add Environment Variable"**:

| Key | Value | Notes |
|-----|-------|-------|
| `ENVIRONMENT` | `production` | Required for production mode |
| `SECRET_KEY` | Generate a secure key | Min 32 characters |
| `DATABASE_URL` | `sqlite:///./data/marketing.db` | SQLite with persistent disk |
| `HTTPS_ONLY` | `false` | Set to `true` for HTTPS only |
| `PYTHON_VERSION` | `3.11` | |

**To generate SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 5: Add Persistent Disk (Required for SQLite)

1. Scroll down to **"Disks"**
2. Click **"Add Disk"**
3. Configure:
   - **Name**: `data`
   - **Mount Path**: `/app/data`
   - **Size**: `1GB` (Free tier max)

### Step 6: Deploy

1. Click **"Create Web Service"**
2. Wait for build to complete (~2-3 minutes)
3. Your service will be live at: `https://exhibition-marketing-automation.onrender.com`

---

## Alternative: Deploy via render.yaml (Blueprint)

With the `render.yaml` file in your repository, Render will auto-detect the configuration:

1. Go to [dashboard.render.com/blueprints](https://dashboard.render.com/blueprints)
2. Click **"New Blueprint Instance"**
3. Connect your GitHub repo
4. Render will show the preview - click **"Apply"**

---

## Verify Deployment

```bash
# Check if service is running
curl https://exhibition-marketing-automation.onrender.com/api/auth/check

# Expected response:
{"authenticated": false}
```

---

## Troubleshooting

### Service Won't Start
- Check **Logs** tab in Render dashboard
- Ensure `SECRET_KEY` is set (required in production)
- Verify `DATABASE_URL` format is correct

### Database Not Persisting
- Make sure the **Disk** is properly mounted at `/app/data`
- Check if `marketing.db` exists in the disk

### Build Fails
- Ensure `requirements.txt` is in the repository root
- Check Python version compatibility

---

## Free Tier Limitations

| Resource | Free Tier Limit |
|----------|-----------------|
| Web Service | 750 hours/month |
| Disk | 1GB |
| Sleep after | 15 min inactivity |

**Note:** Free tier services sleep after 15 minutes of inactivity. To keep it awake, use a free uptime monitoring service like [UptimeRobot](https://uptimerobot.com).

---

## Updating the Service

Since the service is connected to GitHub, simply push to `main`:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

Render will automatically rebuild and deploy.