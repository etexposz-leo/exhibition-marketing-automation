# BoothAS Project Architecture

## Current Modules

### 1. Dashboard
- Overview of all platform metrics
- Clickable stat cards linking to related sections
- Quick actions for common tasks
- Recent activity feed

### 2. Marketing
- Multi-platform social media posting
- Platform adapters for Facebook, LinkedIn, X, Instagram, Google Business
- Content scheduling and publishing
- Campaign management

### 3. Growth Advisor (AI SEO & AEO)
- AI-powered search optimization guidance
- SEO monitoring and recommendations
- Content optimization suggestions
- Visibility tracking across platforms

### 4. Knowledge Base (RAG)
- Document upload and management
- Vector-based semantic search
- AI-powered Q&A from documents
- Manual/instruction ingestion

### 5. Events
- Event creation and management
- Exhibition booth management
- Event-specific marketing campaigns
- Event detail pages

### 6. History
- Scheduled posts tracking
- Published content archive
- Post status monitoring
- Analytics timeline

### 7. Settings
- User profile management
- API key configuration
- SMS verification settings
- Platform integrations

### 8. SMS Verification
- Phone number verification
- Mock mode for development
- Secure code delivery
- Session management

---

## Future Modules

### 1. Compliance Agent
- Regulatory compliance checking
- Content policy enforcement
- Audit trail management

### 2. Design Agent
- AI-powered booth design generation
- Exhibition layout optimization
- Visual asset creation

### 3. Quotation Agent
- Automated quote generation
- Pricing calculator
- Service bundling

### 4. CRM Agent
- Lead management
- Customer relationship tracking
- Contact database

### 5. Publishing Hub
- Centralized content calendar
- Cross-platform scheduling
- Approval workflows

### 6. Analytics Agent
- Advanced reporting
- ROI tracking
- Trend analysis
- Performance dashboards

---

## Technology Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│  (HTML/CSS/JS - Dashboard, Marketing, Events, Knowledge)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   Auth   │ │  Events  │ │  RAG     │ │Marketing │       │
│  │  Routes  │ │  Routes  │ │  Routes  │ │  Routes  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   SQLite    │    │  AI Service  │    │   Platform   │
│   Database  │    │ (OpenAI/DeepSeek)    │   Adapters  │
└──────────────┘    └──────────────┘    └──────────────┘
```

## API Structure
- `/api/auth/*` - Authentication and user management
- `/api/events/*` - Event CRUD operations
- `/api/rag/*` - Knowledge base and RAG operations
- `/api/growth/*` - Growth advisor endpoints
- `/api/routes/*` - Marketing and campaign endpoints
