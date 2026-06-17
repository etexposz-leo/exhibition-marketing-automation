# BoothOS - Exhibition Marketing Automation

## Repository Structure

```
exhibition-marketing-automation/
├── app/
│   ├── api/              # API routes
│   │   ├── event_routes.py  # Event Workspace API
│   │   └── ...
│   ├── core/             # Core utilities
│   ├── models/          # SQLAlchemy models
│   └── main.py          # FastAPI application
├── templates/           # Jinja2 templates
│   ├── events.html      # Event list page
│   ├── event_detail.html # Event detail page
│   ├── event_assistant.html # AI assistant page
│   └── ...
├── data/                # SQLite database
└── requirements.txt
```

## Development

### Start Local Server
```bash
cd /workspace/project/exhibition-marketing-automation
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Key Endpoints
- `/events` - Event list page
- `/events/{id}` - Event detail page
- `/events/{id}/assistant` - Event AI Assistant
- `/api/events` - Event API (GET/POST)
- `/api/events/{id}` - Event CRUD (GET/PUT/DELETE)
- `/api/events/{id}/query` - AI query endpoint

### Database
- SQLite at `data/marketing.db`
- Event tables: `events`, `event_documents`, `event_document_chunks`, `event_queries`

## Project Context

### BoothOS Vision
Transform BoothOS from marketing tool into Event Operating System. Phase 1 implemented:
- **Event Workspace**: Event CRUD, Stats, and AI Assistant
- Event model with name, venue, dates, status, organizer info
- AI-powered event planning assistant using RAG

### Current Phase
Phase 1 (Event Workspace) completed. Future phases will extend event functionality.
