from app.core.log_safety import install
install()
from app.core import cloud_runtime
cloud_runtime.configure()
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from pathlib import Path
from contextlib import asynccontextmanager
import os
import jinja2

from app.core.security import session_options, development_feature
from app.core.ownership import authenticated_session
from app.api.meta_routes import router as meta_router
from app.api.channel_workspace import router as channel_workspace_router
from app.api.unified_marketing import router as unified_marketing_router
from app.api.content_inspiration import router as content_inspiration_router
from app.services.meta_channel import MetaAdapter
from app.api.linkedin_routes import router as linkedin_router
from app.services.linkedin_channel import LinkedInAdapter
from app.services.platform_adapter import PlatformRegistry, PlatformType
PlatformRegistry.register(PlatformType.LINKEDIN, LinkedInAdapter())
PlatformRegistry.register(PlatformType.FACEBOOK, MetaAdapter("facebook"))
PlatformRegistry.register(PlatformType.INSTAGRAM, MetaAdapter("instagram"))
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
    return request.session.get("mfa_verified" if cloud_runtime.enabled() else "sms_verified", False) is True


@asynccontextmanager
async def lifespan(app: FastAPI):
    if cloud_runtime.enabled():
        cloud_runtime.validate_database(engine)
    # Production configuration validation
    import os
    if os.environ.get("ENVIRONMENT") == "production":
        enforce_production_config()
    else:
        print_config_status()
    
    # Startup
    if development_feature("ENABLE_SCHEDULER"):
        await start_scheduler()

    # Create demo account
    db = SessionLocal()
    try:
        if development_feature("ENABLE_DEMO_ACCOUNT"):
            create_demo_account(db)
    finally:
        db.close()

    from app.services.expo_worker import start_local_worker,stop_local_worker
    start_local_worker(SessionLocal)
    try:
        yield
    finally:
        import asyncio
        await asyncio.to_thread(stop_local_worker)
        await stop_scheduler()


app = FastAPI(
    title="Exhibition Marketing Automation",
    version="2.0.0",
    lifespan=lifespan
)

# Add session middleware
SESSION_OPTIONS = session_options()
app.add_middleware(
    SessionMiddleware,
    **SESSION_OPTIONS
)

# Create database tables
# Schema changes are explicit Alembic operations; never mutate storage on import.

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include API routes
app.include_router(meta_router, prefix="/api", dependencies=[Depends(authenticated_session)])
app.include_router(channel_workspace_router, prefix="/api", dependencies=[Depends(authenticated_session)])
app.include_router(unified_marketing_router, prefix="/api", dependencies=[Depends(authenticated_session)])
from app.api.sales_copy import router as sales_copy_router
app.include_router(sales_copy_router, prefix='/api', dependencies=[Depends(authenticated_session)])
from app.api.agent_access import owner_router as agent_grants_router, tool_router as agent_tools_router
app.include_router(agent_grants_router, prefix='/api')
app.include_router(agent_tools_router, prefix='/api')
from app.api.publishing_center import router as publishing_center_router
app.include_router(publishing_center_router, prefix='/api', dependencies=[Depends(authenticated_session)])
from app.api.exhibitor_leads import router as exhibitor_leads_router
from app.api.module_users import router as module_users_router
from app.api.invoice_module import router as invoice_module_router
from app.api.english_module import router as english_module_router
from app.api.quote_module import router as quote_module_router
from app.api.original_software import router as original_software_router
app.include_router(original_software_router,prefix='/api',dependencies=[Depends(authenticated_session)])
app.include_router(invoice_module_router,prefix='/api',dependencies=[Depends(authenticated_session)])
app.include_router(english_module_router,prefix='/api',dependencies=[Depends(authenticated_session)])
app.include_router(quote_module_router,prefix='/api',dependencies=[Depends(authenticated_session)])
app.include_router(module_users_router,prefix='/api',dependencies=[Depends(authenticated_session)])
app.include_router(exhibitor_leads_router, prefix='/api', dependencies=[Depends(authenticated_session)])
app.include_router(content_inspiration_router, prefix="/api", dependencies=[Depends(authenticated_session)])
app.include_router(linkedin_router, prefix="/api", dependencies=[Depends(authenticated_session)])
app.include_router(api_router, prefix="/api", dependencies=[Depends(authenticated_session)])
app.include_router(auth_router, prefix="/api")
app.include_router(growth_router, prefix="/api", dependencies=[Depends(authenticated_session)])
app.include_router(rag_router, prefix="/api/rag", dependencies=[Depends(authenticated_session)])
app.include_router(event_router, prefix="/api", dependencies=[Depends(authenticated_session)])

# Serve main page
@app.get("/")
async def root(request: Request):
    """Main page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return RedirectResponse(url='/marketing' if cloud_runtime.enabled() else '/dashboard')


@app.get("/login")
async def login_page():
    """Login page."""
    return FileResponse(str(BASE_DIR / "templates" / ("cloud_login.html" if cloud_runtime.enabled() else "login.html")))


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
    if require_sms_verified(request):
        return RedirectResponse(url="/dashboard")
    return FileResponse(str(BASE_DIR / "templates" / "verify_phone.html"))


@app.get("/settings")
async def settings_page(request: Request):
    """Settings page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("settings.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Dashboard page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("dashboard.html", {"request": request})


@app.get("/history")
async def history_page(request: Request):
    """History page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("history.html", {"request": request})


@app.get("/growth")
async def growth_page(request: Request):
    """Growth Advisor page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("growth.html", {"request": request})


@app.get("/knowledge-base")
async def knowledge_base_page(request: Request):
    """Knowledge Base page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("knowledge_base.html", {"request": request})


@app.get("/marketing/legacy")
async def legacy_marketing_page(request: Request):
    """Marketing Automation page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("index.html")


@app.get("/events")
async def events_page(request: Request):
    """Events page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("events.html", {"request": request})


@app.get("/events/{event_id}")
async def event_detail_page(request: Request, event_id: int):
    """Event detail page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("event_detail.html", {"request": request, "event_id": event_id})


@app.get("/events/{event_id}/assistant")
async def event_assistant_page(request: Request, event_id: int):
    """Event AI Assistant page - requires authentication and SMS verification."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login")
    if not require_sms_verified(request):
        return RedirectResponse(url="/verify-phone")
    return render_template("event_assistant.html", {"request": request, "event_id": event_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# Do not echo invalid credential inputs or exception bodies to API clients.
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(e['loc']), 'type': e['type'], 'msg': 'Invalid input'} for e in exc.errors()]})

@app.exception_handler(ValueError)
async def safe_value_error(request, exc):
    return JSONResponse(status_code=400, content={'detail': 'Invalid operation or unavailable configuration'})

@app.exception_handler(Exception)
async def safe_unhandled_error(request, exc):
    return JSONResponse(status_code=500, content={'detail': 'Operation failed; diagnostic details withheld'})


@app.middleware('http')
async def suppress_unhandled_diagnostics(request, call_next):
    # Starlette's default error middleware re-raises after sending its response;
    # catch here so a server logger cannot expose SQL parameters/provider bodies.
    try:
        return await call_next(request)
    except Exception:
        return JSONResponse(status_code=500, content={'detail': 'Operation failed; diagnostic details withheld'})


@app.get('/linkedin')
async def linkedin_page(request: Request):
    if not require_auth(request):
        return RedirectResponse('/login')
    return render_template('linkedin.html')

@app.get('/health/live')
async def health_live():
    return {'status': 'ok', 'service': 'marketing-automation'}

@app.get("/meta")
async def meta_page(request: Request):
    if not require_auth(request): return RedirectResponse("/login" if cloud_runtime.enabled() else "/acceptance/login?next=meta")
    return render_template("meta.html")

@app.get('/channels')
async def channels_page(request: Request):
    if not require_auth(request): return RedirectResponse('/login' if cloud_runtime.enabled() else '/acceptance/login?next=meta')
    return render_template('channels.html')

@app.get('/marketing')
async def marketing_page(request: Request):
    login='/login' if cloud_runtime.enabled() else '/acceptance/login?next=marketing'
    if not require_auth(request):return RedirectResponse(login)
    if cloud_runtime.enabled() and not require_sms_verified(request):return RedirectResponse('/login')
    return render_template('marketing.html', {'marketing_login_url':login})

@app.get('/marketing/backlinks')
async def marketing_backlinks_page(request: Request):
    if cloud_runtime.enabled():return HTMLResponse('Backlink backend is local-only; cloud bridge not configured',status_code=503)
    if not require_auth(request):return RedirectResponse('/acceptance/login?next=marketing')
    from app.api.unified_marketing import config
    if request.session.get('user_id')!=config()['backlink_owner_id']:return HTMLResponse('Owner access required',status_code=403)
    root=Path(config()['backlink_root'])
    source=(root/'ui/dashboard.html').read_text(encoding='utf-8').replace('<body>','<body data-api="/api/marketing/backlinks/review">').replace('href="review.css"','href="/marketing/backlink-assets/review.css"').replace('src="review.js"','src="/marketing/backlink-assets/review.js"')
    return HTMLResponse(source,headers={'Cache-Control':'no-store'})

@app.get('/marketing/backlink-assets/{name}')
async def marketing_backlink_asset(name:str,request:Request):
    if cloud_runtime.enabled():return HTMLResponse('Cloud Backlink assets not configured',status_code=503)
    if not require_auth(request):return HTMLResponse('Authentication required',status_code=401)
    if name not in {'review.js','review.css'}:return HTMLResponse('Not found',status_code=404)
    from app.api.unified_marketing import config
    return FileResponse(Path(config()['backlink_root'])/'ui'/name)

from app.api.expo_module import router as expo_module_router
app.include_router(expo_module_router,prefix="/api",dependencies=[Depends(authenticated_session)])

from app.api.tiktok_routes import router as tiktok_router
app.include_router(tiktok_router, prefix='/api', dependencies=[Depends(authenticated_session)])

@app.get('/tiktok')
async def tiktok_page(request: Request):
    if not require_auth(request):
        return RedirectResponse('/login')
    return render_template('tiktok.html')
