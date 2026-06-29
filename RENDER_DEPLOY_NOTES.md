# Render Deployment Notes

## Current Status: ✅ Deployed

**Live URL**: https://exhibition-marketing-automation.onrender.com

---

## 🚀 Deployment Steps

### 1. Push to GitHub

```bash
# Stage all changes
git add .

# Commit with descriptive message
git commit -m "Add Marketing Automation Center with draft management, approval queue, and mock publishers"

# Push to GitHub
git push origin main
```

Render automatically deploys on push to `main`.

### 2. Render Auto-Deploy

Render is configured to:
- Watch the `main` branch
- Auto-deploy on push
- Run build command: `pip install -r requirements.txt`
- Run start command: `gunicorn app.main:app --workers 2 --threads 4 --bind 0.0.0.0:10000`

---

## 🔧 Environment Variables

### Required on Render

| Variable | Value | Description |
|----------|-------|-------------|
| `ENVIRONMENT` | `production` | Enable production mode |
| `SECRET_KEY` | `<generate-secure-key>` | Session secret (generate new!) |
| `DATABASE_URL` | `sqlite:///data/marketing.db` | SQLite database |

### Optional (Growth Advisor)

| Variable | Value | Description |
|----------|-------|-------------|
| `OPENAI_API_KEY` | `sk-...` | For content generation |
| `DEEPSEEK_API_KEY` | `...` | For DeepSeek monitoring |
| `GOOGLE_SEARCH_CONSOLE_CREDENTIALS` | `{...}` | For Google SEO tracking |

### DO NOT SET (Security)

| Variable | Why Not |
|----------|---------|
| `GOOGLE_ADS_API_KEY` | Not connected |
| `LINKEDIN_ACCESS_TOKEN` | Not connected |
| `META_ACCESS_TOKEN` | Not connected |
| Any API keys | No real APIs enabled |

---

## 📁 Key Files for Deployment

### Gunicorn Config
```python
# render.yaml or gunicorn.conf.py
bind = "0.0.0.0:10000"
workers = 2
threads = 4
timeout = 120
```

### Start Command
```bash
gunicorn app.main:app --workers 2 --threads 4 --bind 0.0.0.0:10000
```

### Build Command
```bash
pip install -r requirements.txt
```

---

## 🗄️ Database

### SQLite on Render
- Database stored at: `/data/marketing.db`
- Persistent disk attached to Render service
- Automatic backups via Render

### Migration
```bash
# Run migrations on deploy (add to build command)
alembic upgrade head
```

---

## 🌐 Health Check

### Endpoint
```
GET https://exhibition-marketing-automation.onrender.com/api/auth/me
```

### Expected Response
```json
{
  "user": null,
  "authenticated": false
}
```

---

## 📊 Post-Deploy Checklist

- [ ] Login page loads: https://exhibition-marketing-automation.onrender.com/login
- [ ] Demo login works: demo@example.com / demo123
- [ ] Dashboard loads after login
- [ ] Marketing Drafts page accessible: /marketing/drafts
- [ ] Approval Queue page accessible: /marketing/approval
- [ ] Marketing Calendar page accessible: /marketing/calendar
- [ [ ] Marketing Reports page accessible: /marketing/reports
- [ ] Safety banner visible on marketing pages
- [ ] Can create a test draft
- [ ] Can submit draft for approval
- [ ] Mock publish works (dry-run only)
- [ ] No real API calls made
- [ ] No costs incurred

---

## 🔐 Security Notes

### Current Configuration
- ✅ No real API keys stored
- ✅ No credentials in code
- ✅ Mock publishers only
- ✅ Human approval required
- ✅ Session-based auth

### Render Security Features
- ✅ HTTPS enforced
- ✅ Environment variables for secrets
- ✅ Disk encryption
- ✅ No exposed credentials

### What NOT to Do
- ❌ Don't add real API tokens to Render
- ❌ Don't commit credentials to GitHub
- ❌ Don't share admin passwords
- ❌ Don't disable safety checks

---

## 🐛 Troubleshooting

### Deployment Failed
1. Check Render build logs
2. Verify `requirements.txt` is valid
3. Check Python version compatibility
4. Ensure all imports resolve

### 500 Error on Pages
1. Check server logs
2. Verify database exists
3. Check environment variables
4. Review recent code changes

### Login Not Working
1. Clear browser cookies
2. Check session configuration
3. Verify database connection
4. Check server time synchronization

---

## 🔄 Rolling Back

### Via Render Dashboard
1. Go to Render dashboard
2. Select your service
3. Go to "Deploys"
4. Click "Redeploy" on a previous commit

### Via Git
```bash
# Revert to previous commit
git revert HEAD
git push origin main
```

---

## 📈 Monitoring

### Render Dashboard
- Deployment status
- Server logs
- Metrics (CPU, RAM, Bandwidth)
- Error tracking

### Application Logs
```bash
# View logs via SSH (if enabled)
render logs
```

---

## 💰 Cost

### Current Plan
- **Service Type**: Starter ($7/month)
- **Includes**: 512 MB RAM, 0.5 CPU, 1 GB disk
- **Bandwidth**: 100 GB/month

### Expected Usage
- **Memory**: ~200 MB typical
- **CPU**: < 20% typical
- **Disk**: < 100 MB for SQLite
- **Cost**: $0 for mock mode (no API calls)

---

## 🔧 Maintenance

### Regular Tasks
- [ ] Check deployment status weekly
- [ ] Review error logs monthly
- [ ] Update dependencies quarterly
- [ ] Review security settings
- [ ] Backup verification

### Dependency Updates
```bash
# Check for updates
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Update all
pip install --upgrade -r requirements.txt
```

---

## 📞 Support

### Render Support
- Dashboard: https://dashboard.render.com
- Docs: https://render.com/docs
- Support: support@render.com

### Application Issues
- Check logs first
- Review this document
- Check GitHub issues
- Contact: admin@example.com

---

## 📝 Deployment History

| Date | Version | Commit | Notes |
|------|---------|--------|-------|
| 2026-06-15 | 3.0.0 | HEAD | Marketing Center with draft management |
| 2026-06-15 | 2.0.0 | prev | Growth Advisor added |
| 2026-06-15 | 1.0.0 | prev | Initial deployment |

---

## ✅ Last Verified

**Date**: 2026-06-15
**Status**: ✅ All checks passed
- Login page loads ✅
- Demo account works ✅
- Marketing pages accessible ✅
- Mock publishers functional ✅
- No real API calls ✅
- No costs incurred ✅
