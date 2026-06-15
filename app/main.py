from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from contextlib import asynccontextmanager

from app.api.routes import router as api_router
from app.core.database import engine, Base
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await start_scheduler()
    yield
    # Shutdown
    await stop_scheduler()


app = FastAPI(
    title="Exhibition Marketing Automation", 
    version="2.0.0",
    lifespan=lifespan
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Mount static files
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    return FileResponse(str(BASE_DIR / "templates" / "index.html"))


@app.get("/index.html")
async def index():
    return FileResponse(str(BASE_DIR / "templates" / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
