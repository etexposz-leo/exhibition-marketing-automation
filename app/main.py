from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from contextlib import asynccontextmanager
import uuid

from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.core.database import engine, Base, SessionLocal
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.auth import create_demo_account
from starlette.middleware.sessions import SessionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.add_middleware(
    SessionMiddleware,
    secret_key=str(uuid.uuid4()),  # Use a fixed key for development
    max_age=86400,  # 24 hours
    same_site="lax"
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Mount static files
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include API routes
app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")


@app.get("/")
async def root(request: Request):
    """Root page - redirect to index or login based on session."""
    if request.session.get("user_id"):
        return FileResponse(str(BASE_DIR / "templates" / "index.html"))
    return RedirectResponse(url="/login")


@app.get("/index.html")
async def index(request: Request):
    """Index page - redirect to login if not authenticated."""
    if request.session.get("user_id"):
        return FileResponse(str(BASE_DIR / "templates" / "index.html"))
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page():
    """Login page."""
    return FileResponse(str(BASE_DIR / "templates" / "login.html"))


@app.get("/register")
async def register_page():
    """Register page."""
    return FileResponse(str(BASE_DIR / "templates" / "register.html"))


@app.get("/settings")
async def settings_page(request: Request):
    """Settings page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "settings.html"))


@app.get("/history")
async def history_page(request: Request):
    """History page - requires authentication."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    return FileResponse(str(BASE_DIR / "templates" / "history.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
