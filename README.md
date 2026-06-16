# Exhibition Marketing Automation System

AI-powered marketing content generation and social media publishing platform for exhibition booth design companies.

## Features

### 🎯 Core Features
- **Industry-specific content generation** for exhibition marketing
- **Multi-platform publishing** to LinkedIn, Facebook, Instagram, X (Twitter), Google Business
- **Platform-specific content optimization** (character limits, hashtags, style adjustments)
- **Preview before publish** workflow
- **Scheduled publishing** with APScheduler
- **Mock publishing mode** (works without API credentials)
- **User authentication** with session management
- **User data isolation** for multi-tenant security

### 📊 Growth Advisor (NEW!)
- **Google SEO Monitoring** - Track keyword rankings, impressions, CTR, and position trends
- **ChatGPT Visibility Monitoring** - Check if your brand appears in AI-generated responses
- **DeepSeek Visibility Monitoring** - Monitor visibility on emerging AI platforms
- **Competitor Tracking** - Track competitor mentions in AI results
- **Daily Growth Reports** - Get actionable recommendations and next-step action plans
- **Mock Mode** - Works without API credentials for testing

### 🔐 Authentication
- Session-based authentication (no JWT)
- Bcrypt password hashing
- Demo account for testing

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Copy environment file
cp .env.example .env

# Start with Docker Compose
docker-compose up -d

# Open browser
http://localhost:8000
```

### Option 2: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Run server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Open browser
http://localhost:8000
```

## Demo Account

- **Email**: demo@example.com
- **Password**: demo123

The demo account comes with:
- Sample campaigns (CES 2026, Medica 2026)
- Sample content (LinkedIn, Facebook, Google Business posts)
- Sample scheduled posts
- Demo SEO keywords (5 keywords for exhibition booth industry)
- Demo competitors (5 major competitors)

## Pages

| Page | Description |
|------|-------------|
| `/` | Dashboard (requires login) |
| `/login` | Login page |
| `/register` | Registration page |
| `/dashboard` | Statistics dashboard |
| `/settings` | API keys and platform settings |
| `/history` | Publishing history |
| `/growth` | Growth Advisor (SEO & AI visibility) |

## API Endpoints

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Login with email/password |
| `/api/auth/register` | POST | Register new user |
| `/api/auth/logout` | POST | Logout current user |
| `/api/auth/check` | GET | Check authentication status |
| `/api/auth/me` | GET | Get current user info |

### Campaign Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/generate` | POST | Generate marketing content |
| `/api/campaigns` | GET | List user's campaigns |
| `/api/campaigns/{id}` | GET | Get campaign details |
| `/api/campaigns/{id}` | DELETE | Delete campaign |

### Content Optimization
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/campaigns/{id}/optimize` | POST | Optimize content for platforms |
| `/api/campaigns/{id}/preview` | POST | Preview optimized content |
| `/api/campaigns/{id}/publish` | POST | Publish to platforms |

### Publishing
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scheduled-posts` | GET | List scheduled posts |
| `/api/scheduled-posts` | POST | Create scheduled post |
| `/api/scheduled-posts/{id}` | DELETE | Delete scheduled post |

### Settings
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings/platforms-status` | GET | Platform status |
| `/api/settings/social-accounts` | GET/POST | Manage social accounts |
| `/api/settings/api-keys` | POST | Save AI API keys |

### Growth Advisor
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/growth/keywords` | GET | List tracked keywords |
| `/api/growth/keywords` | POST | Add new keyword |
| `/api/growth/keywords/{id}` | PUT | Update keyword |
| `/api/growth/keywords/{id}` | DELETE | Delete keyword |
| `/api/growth/competitors` | GET | List competitors |
| `/api/growth/competitors` | POST | Add competitor |
| `/api/growth/check-now` | POST | Run full growth check |
| `/api/growth/report` | GET | Get latest daily report |
| `/api/growth/recommendations` | GET | Get recommendations |
| `/api/growth/metrics/seo` | GET | Get SEO metrics |
| `/api/growth/metrics/ai-visibility` | GET | Get AI visibility metrics |
| `/api/growth/status` | GET | Get API configuration status |

## Growth Advisor

The Growth Advisor helps exhibition booth companies monitor their online presence across Google SEO and AI platforms.

### How It Works

#### Google SEO Monitoring
- Tracks keyword rankings in Google search results
- Monitors impressions, clicks, and CTR
- Records position trends over time
- Uses Google Search Console API if configured, otherwise mock mode

#### ChatGPT Visibility
- Checks if your brand appears in ChatGPT responses
- Detects brand mentions: ET-EXPO, et-expo.com, etexpous.com, www.et-expo.com, www.etexpous.com
- Identifies competitor mentions in AI responses
- Generates visibility score (0-100)

#### DeepSeek Visibility
- Same as ChatGPT but for DeepSeek platform
- Monitors emerging AI search visibility
- Tracks brand and competitor mentions

### Mock Mode

When API credentials are not configured, the Growth Advisor operates in mock mode:

- **Mock SEO data**: Generates realistic ranking positions, impressions, and CTR
- **Mock AI visibility**: Simulates brand visibility in AI responses
- **Mock competitor mentions**: Shows sample competitor data

Mock mode is perfect for testing and demonstration purposes.

### Daily Schedule

The Growth Advisor runs a daily check at **08:00 UTC** automatically:

1. Checks all active keywords for Google rankings
2. Queries ChatGPT for visibility
3. Queries DeepSeek for visibility
4. Generates updated recommendations
5. Creates daily growth report

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# Show current version
alembic current
```

## Configuration

### Environment Variables
```bash
# Application Settings
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///./data/marketing.db

# AI Services (optional)
OPENAI_API_KEY=sk-...          # Content generation + ChatGPT monitoring
DEEPSEEK_API_KEY=...           # DeepSeek monitoring

# Growth Advisor (optional)
GOOGLE_SEARCH_CONSOLE_CREDENTIALS={"type":"service_account",...}  # Google SEO monitoring

# Social Platforms (optional - mock mode works without these)
LINKEDIN_ACCESS_TOKEN=...
FACEBOOK_ACCESS_TOKEN=...
X_BEARER_TOKEN=...
GOOGLE_BUSINESS_API_KEY=...
```

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, APScheduler, Starlette Sessions
- **Database**: SQLite (default), PostgreSQL (production)
- **Migrations**: Alembic
- **Frontend**: Vanilla JS, CSS
- **Auth**: Bcrypt, SessionMiddleware
- **Container**: Docker, Docker Compose

## License

MIT
