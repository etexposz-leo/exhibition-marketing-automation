# Production Deployment Checklist

This checklist ensures a secure and stable production deployment of the Exhibition Marketing Automation System.

---

## 1. Environment Configuration

### Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ENVIRONMENT` | ✅ Yes | Set to `production` |
| `SECRET_KEY` | ✅ Yes | Min 32 characters, use `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | ✅ Yes | PostgreSQL recommended: `postgresql://user:pass@host/db` |
| `HTTPS_ONLY` | Recommended | Set to `true` for HTTPS enforcement |

### Generate Secure SECRET_KEY

```bash
# Generate a secure key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Or for Docker
docker run --rm python:3.11-slim python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Create Production .env File

```bash
# Copy the example
cp .env.example .env

# Edit with production values
nano .env
```

Required changes in `.env`:
```env
ENVIRONMENT=production
SECRET_KEY=<generated-secure-key-at-least-32-chars>
DATABASE_URL=postgresql://user:password@host:5432/marketing
HTTPS_ONLY=true
```

---

## 2. Database Setup

### Option A: PostgreSQL (Recommended)

```bash
# Using Docker Compose
# Uncomment the db service in docker-compose.yml

# Or manually
docker run -d \
  --name marketing-db \
  -e POSTGRES_DB=marketing \
  -e POSTGRES_USER=marketing \
  -e POSTGRES_PASSWORD=<strong-password> \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine
```

### Database Migration

```bash
# Apply migrations
alembic upgrade head

# Verify
alembic current
```

### Update DATABASE_URL for PostgreSQL

```env
DATABASE_URL=postgresql://marketing:<password>@localhost:5432/marketing
```

---

## 3. Security Configuration

### [ ] Generate New SECRET_KEY

The default development key MUST be replaced:

```env
# WRONG - Will cause app to refuse to start
SECRET_KEY=dev-secret-key-change-in-production

# CORRECT - Generate and use a secure key
SECRET_KEY=<output-from-generate-command>
```

### [ ] Enable HTTPS

For production, set `HTTPS_ONLY=true`:

```env
HTTPS_ONLY=true
```

### [ ] Delete Demo Account

```bash
# Login and delete via API, or directly in database
docker exec -it exhibition-marketing-app python -c "
from app.core.database import SessionLocal
from app.models.models import User
db = SessionLocal()
demo = db.query(User).filter(User.email == 'demo@example.com').first()
if demo:
    db.delete(demo)
    db.commit()
    print('Demo account deleted')
db.close()
"
```

### [ ] Review User Permissions

Ensure all users have appropriate access levels.

---

## 4. Docker Deployment

### [ ] Build Image

```bash
# Build the image
docker-compose build

# Or just pull latest if using pre-built
docker-compose pull
```

### [ ] Start Services

```bash
# Start in detached mode
docker-compose up -d

# Check logs
docker-compose logs -f app
```

### [ ] Verify Health

```bash
# Check container health
docker-compose ps

# Test API
curl http://localhost:8000/api/auth/check
# Should return: {"authenticated": false}
```

### [ ] Run Database Migrations

```bash
# Apply any pending migrations
docker-compose exec app alembic upgrade head
```

---

## 5. Post-Deployment Verification

### [ ] Test Authentication

```bash
# Register a new user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","username":"Admin","password":"<secure-password>","company_name":"Your Company"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"admin@example.com","password":"<password>"}'

# Verify authenticated
curl -b cookies.txt http://localhost:8000/api/auth/me
```

### [ ] Test Campaign Creation

```bash
# Create a test campaign
curl -X POST "http://localhost:8000/api/generate?use_ai=false" \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"customer_industry":"Technology","exhibition_name":"Test Expo 2025"}'
```

### [ ] Verify Settings Page

Navigate to `http://localhost:8000/settings` and verify:
- [ ] Login required
- [ ] Platform status displayed
- [ ] Save credentials works

### [ ] Verify Dashboard

Navigate to `http://localhost:8000/dashboard` and verify:
- [ ] Login required
- [ ] Stats displayed
- [ ] Recent activity shown

---

## 6. Monitoring Setup

### [ ] Configure Log Rotation

```bash
# Add to docker-compose.yml under volumes:
# - ./logs:/app/logs

# Create logrotate config
sudo nano /etc/logrotate.d/marketing-app
```

Contents:
```
./logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 appuser appuser
}
```

### [ ] Set Up Health Monitoring

```bash
# Check container health status
docker inspect --format='{{.State.Health.Status}}' exhibition-marketing-app

# Should return: healthy
```

### [ ] Configure Backup

```bash
# Backup database daily
0 2 * * * docker exec exhibition-marketing-db pg_dump -U marketing marketing > /backups/marketing-$(date +\%Y\%m\%d).sql
```

---

## 7. Performance Checklist

### [ ] Enable Query Logging (Staging Only)

```env
# Only in non-production
SQLALCHEMY_ECHO=false
```

### [ ] Configure Connection Pooling

For PostgreSQL, update `DATABASE_URL`:
```
postgresql://user:pass@host:5432/marketing?pool_size=10&max_overflow=20
```

### [ ] Set Memory Limits

```yaml
# In docker-compose.yml
deploy:
  resources:
    limits:
      memory: 512M
    reservations:
      memory: 256M
```

---

## 8. Troubleshooting

### App Refuses to Start

**Error:** `EnvironmentError: SECRET_KEY is required in production`

**Fix:** Set `SECRET_KEY` in environment:
```bash
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
docker-compose up -d
```

### Database Connection Failed

**Error:** `Could not connect to database`

**Fix:** Check DATABASE_URL and database accessibility:
```bash
# Test connection
docker-compose exec app python -c "from sqlalchemy import create_engine; engine = create_engine('$DATABASE_URL'); print(engine.connect())"
```

### 502 Bad Gateway

**Error:** Nginx returns 502

**Fix:** Check if app container is healthy:
```bash
docker-compose logs app
docker-compose exec app curl localhost:8000/api/auth/check
```

---

## Quick Start Commands

```bash
# 1. Clone and configure
git clone <repo-url>
cd exhibition-marketing-automation
cp .env.example .env

# 2. Edit .env with production values
nano .env

# 3. Generate secret key
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "SECRET_KEY=$SECRET_KEY" >> .env
echo "ENVIRONMENT=production" >> .env
echo "DATABASE_URL=postgresql://user:pass@localhost:5432/marketing" >> .env

# 4. Start services
docker-compose up -d

# 5. Run migrations
docker-compose exec app alembic upgrade head

# 6. Verify
curl http://localhost:8000/api/auth/check
```

---

## Pre-Flight Check

Run this script before deploying:

```bash
#!/bin/bash
echo "=== Production Deployment Pre-Flight Check ==="

# Check SECRET_KEY
if [ -z "$SECRET_KEY" ]; then
    echo "❌ SECRET_KEY not set"
    exit 1
elif [ ${#SECRET_KEY} -lt 32 ]; then
    echo "❌ SECRET_KEY must be at least 32 characters"
    exit 1
fi
echo "✅ SECRET_KEY configured"

# Check DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not set"
    exit 1
fi
echo "✅ DATABASE_URL configured"

# Check ENVIRONMENT
if [ "$ENVIRONMENT" != "production" ]; then
    echo "⚠️  ENVIRONMENT is not 'production'"
fi
echo "✅ ENVIRONMENT=$ENVIRONMENT"

echo ""
echo "=== All checks passed ==="
```

---

## Support

For issues, check:
1. Container logs: `docker-compose logs -f`
2. API health: `curl http://localhost:8000/api/auth/check`
3. Database: `docker-compose exec app alembic current`