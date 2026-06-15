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

### 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                            │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │  Campaign   │   Content   │   Platform  │  Scheduler  │ │
│  │  Manager    │  Generator  │   Adapter   │   Service   │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Social Platforms                           │
│  LinkedIn │ Facebook │ Instagram │ X (Twitter) │ Google   │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Open browser
http://localhost:8000
```

## API Endpoints

### Campaign Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/generate` | POST | Generate marketing content |
| `/api/campaigns` | GET | List all campaigns |
| `/api/campaigns/{id}` | GET | Get campaign details |
| `/api/campaigns/{id}/contents` | GET | Get campaign content |

### Content Optimization
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/optimize` | POST | Optimize content for platforms |
| `/api/campaigns/{id}/optimize` | POST | Optimize and save content |
| `/api/campaigns/{id}/preview` | POST | Preview optimized content |
| `/api/campaigns/{id}/optimized` | GET | Get optimized content |

### Publishing
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/publish/batch` | POST | Publish to multiple platforms |
| `/api/publish/{platform}` | POST | Publish to single platform |
| `/api/campaigns/{id}/publish` | POST | Publish campaign |

### Platforms
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/platforms` | GET | List all platforms |
| `/api/platforms-status` | GET | Platform configuration status |

### Settings
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings/social-accounts` | GET/POST | Manage social accounts |
| `/api/settings/platforms-status` | GET | Platform status |

## Platform Adapter Architecture

Each platform implements the unified `BasePlatformAdapter` interface:

```python
class BasePlatformAdapter(ABC):
    async def publish(content, **kwargs) -> PublishResult
    def publish_sync(content, **kwargs) -> PublishResult
    def is_configured() -> bool
    def validate_content(content) -> tuple[bool, str]
```

### Supported Platforms

| Platform | Character Limit | Images | Style |
|----------|---------------|--------|-------|
| LinkedIn | 3,000 | ❌ | Professional B2B |
| Facebook | 63,206 | ✅ | General Marketing |
| Instagram | 2,200 | ✅ | Visual + Hashtags |
| X (Twitter) | 280 | ❌ | Short & Punchy |
| Google Business | 1,500 | ❌ | Local SEO |

## Database Models

- **Campaign** - Marketing campaigns with industry/exhibition info
- **GeneratedContent** - AI-generated content
- **OptimizedContent** - Platform-specific optimized content
- **ScheduledPost** - Posts with scheduling info
- **SocialAccount** - Platform credentials (mock mode by default)
- **ContentTemplate** - Reusable content templates

## Configuration

### Environment Variables (optional)
```bash
# AI Services
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...

# Social Platforms (optional - mock mode works without these)
LINKEDIN_ACCESS_TOKEN=...
FACEBOOK_ACCESS_TOKEN=...
INSTAGRAM_ACCESS_TOKEN=...
X_BEARER_TOKEN=...
GOOGLE_BUSINESS_API_KEY=...
```

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, APScheduler
- **Database**: SQLite (default), PostgreSQL (production)
- **Frontend**: Vanilla JS, CSS
- **AI**: OpenAI GPT-4, DeepSeek (configurable)

## License

MIT