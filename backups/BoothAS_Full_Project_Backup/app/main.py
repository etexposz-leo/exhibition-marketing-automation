from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from pathlib import Path
from contextlib import asynccontextmanager
import os
import jinja2

from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.api.growth_routes import router as growth_router
from app.api.rag_routes import router as rag_router
from app.api.event_routes import router as event_router
from app.core.database import engine, Base, SessionLocal
from app.core.config import enforce_production_config, print_config_status
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.auth import create_demo_account
from starlette.middleware.sessions import SessionMiddleware

# Template directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Create Jinja2 environment
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=jinja2.select_autoescape(['html', 'xml'])
)

def render_template(template_name: str, context: dict = None) -> HTMLResponse:
    """Render a Jinja2 template and return HTML response."""
    template = jinja_env.get_template(template_name)
    html_content = template.render(context or {})
    return HTMLResponse(content=html_content)


def require_auth(request: Request) -> bool:
    """Check if user is authenticated."""
    return request.session.get("user_id") is not None


def require_sms_verified(request: Request) -> bool:
    """Check if user has completed SMS verification."""
    return request.session.get("sms_verified", False) is True


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production configuration validation
    import os
    if os.environ.get("ENVIRONMENT") == "production":
        enforce_production_config()
    else:
        print_config_status()
    
    # Startup
    await start_scheduler()

    # Create demo account
    db = SessionLocal()
    try:
        create_demo_account(db)
    finally:
        db.close()

    yield
    # Shutdown
    await stop_scheduler()


app = FastAPI(
    title="Exhibition Marketing Automation",
    version="2.0.0",
    lifespan=lifespan
)

# Add session middleware
SESSION_SECRET = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=86400,  # 24 hours
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include API routes
app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(growth_router, prefix="/api")
app.include_router(rag_router, prefix="/api/rag")
app.include_router(event_router, prefix="/api")

# Serve main page
@app.get("/")
async def root(request: Request):
    """Main page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return RedirectResponse(url="/dashboard")


@app.get("/login")
async def login_page():
    """Login page."""
    return FileResponse(str(BASE_DIR / "templates" / "login.html"))


@app.get("/register")
async def register_page():
    """Registration page."""
    return FileResponse(str(BASE_DIR / "templates" / "register.html"))


@app.get("/verify-phone")
async def verify_phone_page(request: Request):
    """Phone verification page - requires login but not SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    # If already verified, redirect to dashboard
    if request.session.get("sms_verified"):
        return RedirectResponse(url="/dashboard")
    return FileResponse(str(BASE_DIR / "templates" / "verify_phone.html"))


@app.get("/settings")
async def settings_page(request: Request):
    """Settings page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("settings.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Dashboard page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("dashboard.html", {"request": request})


@app.get("/history")
async def history_page(request: Request):
    """History page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("history.html", {"request": request})


@app.get("/growth")
async def growth_page(request: Request):
    """Growth Advisor page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("growth.html", {"request": request})


@app.get("/knowledge-base")
async def knowledge_base_page(request: Request):
    """Knowledge Base page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("knowledge_base.html", {"request": request})


@app.get("/marketing")
async def marketing_page(request: Request):
    """Marketing Automation page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return RedirectResponse(url="/dashboard")


@app.get("/events")
async def events_page(request: Request):
    """Events page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("events.html", {"request": request})


@app.get("/events/{event_id}")
async def event_detail_page(request: Request, event_id: int):
    """Event detail page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("event_detail.html", {"request": request, "event_id": event_id})


@app.get("/events/{event_id}/assistant")
async def event_assistant_page(request: Request, event_id: int):
    """Event AI Assistant page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not request.session.get("sms_verified"):
        return RedirectResponse(url="/verify-phone")
    return render_template("event_assistant.html", {"request": request, "event_id": event_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
