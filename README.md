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

### 🔐 Authentication
- Session-based authentication (no JWT)
- Bcrypt password hashing
- Demo account for testing

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Open browser
http://localhost:8000
```

## Demo Account

- **Email**: demo@example.com
- **Password**: demo123

The demo account comes with sample campaigns and scheduled posts for testing.

## Pages

| Page | Description |
|------|-------------|
| `/` | Dashboard (requires login) |
| `/login` | Login page |
| `/register` | Registration page |
| `/settings` | Social media account settings |
| `/history` | Publishing history |

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

## Database Models

| Model | Description |
|-------|-------------|
| **User** | User accounts with hashed passwords |
| **Campaign** | Marketing campaigns (user_id linked) |
| **GeneratedContent** | AI-generated content (user_id linked) |
| **OptimizedContent** | Platform-optimized content (user_id linked) |
| **ScheduledPost** | Scheduled posts (user_id linked) |
| **SocialAccount** | Platform credentials (user_id linked) |
| **ContentTemplate** | Reusable templates |

## Data Isolation

All data is isolated by `user_id`:
- Users can only view and manage their own campaigns
- Scheduled posts are scoped to the authenticated user
- Social account credentials are private to each user
- API returns 401 for unauthenticated requests

## Configuration

### Environment Variables (optional)
```bash
# AI Services
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...

# Social Platforms (optional - mock mode works without these)
LINKEDIN_ACCESS_TOKEN=...
FACEBOOK_ACCESS_TOKEN=...
```

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, APScheduler, Starlette Sessions
- **Database**: SQLite
- **Frontend**: Vanilla JS, CSS
- **Auth**: Bcrypt, SessionMiddleware

## License

MIT
