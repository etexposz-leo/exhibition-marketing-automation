from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from contextlib import asynccontextmanager
import os

from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.api.growth_routes import router as growth_router
from app.core.database import engine, Base, SessionLocal
from app.core.config import enforce_production_config, print_config_status
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.auth import create_demo_account
from starlette.middleware.sessions import SessionMiddleware


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
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include API routes
app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(growth_router, prefix="/api")

# Serve main page
@app.get("/")
async def root(request: Request):
    """Main page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "index.html"))


@app.get("/login")
async def login_page():
    """Login page."""
    return FileResponse(str(BASE_DIR / "templates" / "login.html"))


@app.get("/register")
async def register_page():
    """Registration page."""
    return FileResponse(str(BASE_DIR / "templates" / "register.html"))


@app.get("/settings")
async def settings_page(request: Request):
    """Settings page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "settings.html"))


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Dashboard page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "dashboard.html"))


@app.get("/history")
async def history_page(request: Request):
    """History page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "history.html"))


@app.get("/growth")
async def growth_page(request: Request):
    """Growth Advisor page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "growth.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
