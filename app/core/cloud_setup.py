"""Closed bootstrap app. No marketing APIs, scheduler, or business DB access on boot."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


class Begin(BaseModel):
    setup_key: str = Field(min_length=32, max_length=200)


class Finish(BaseModel):
    ticket: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=16, max_length=72)
    repeat_password: str = Field(min_length=16, max_length=72)
    code: str = Field(pattern=r'^\d{6}$')


def create_setup_app(runtime):
    runtime = Path(runtime)
    if not runtime.is_absolute() or runtime.is_symlink() or not runtime.parent.is_dir():
        raise RuntimeError('Protected persistent directory required')
    keyfile = runtime.parent / '.owner-setup-key'
    if keyfile.is_symlink():
        raise RuntimeError('Invalid setup key file')
    try:
        fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_urlsafe(48))
    if os.name != 'nt' and keyfile.stat().st_mode & 0o077:
        raise RuntimeError('Setup key must be private')
    key = keyfile.read_text().strip()
    if len(key) < 32:
        raise RuntimeError('Invalid setup key')
    from app.core.cloud_runtime import base_url
    origin = base_url()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    pending = {}
    attempts = []
    lock = threading.Lock()

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers.update({'Cache-Control':'no-store', 'X-Frame-Options':'DENY',
            'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    def guard(request):
        if runtime.exists():
            raise HTTPException(409, 'Setup already completed; restart service to activate')
        if request.headers.get('origin') != origin:
            raise HTTPException(403, 'Origin rejected')
        now = time.monotonic()
        attempts[:] = [x for x in attempts if now-x < 900]
        if len(attempts) >= 20:
            raise HTTPException(429, 'Wait 15 minutes before retrying')
        attempts.append(now)

    @app.get('/health/live')
    def health():
        return {'status':'ok', 'mode':'owner_setup_required', 'release':'marketing-cloud-bootstrap-20261007', 'real_publishing':False}

    @app.get('/')
    @app.get('/login')
    @app.get('/marketing')
    def page():
        return FileResponse(Path(__file__).resolve().parents[2]/'templates'/'cloud_setup.html')

    @app.get('/setup.js')
    def js():
        return FileResponse(Path(__file__).resolve().parents[2]/'static'/'js'/'cloud-setup.js',media_type='text/javascript')

    @app.post('/setup/begin')
    def begin(data: Begin, request: Request):
        with lock:
            guard(request)
            if not hmac.compare_digest(hashlib.sha256(data.setup_key.encode()).digest(),hashlib.sha256(key.encode()).digest()):
                raise HTTPException(403,'Setup key rejected')
            pending.clear()
            ticket = secrets.token_urlsafe(48)
            secret = base64.b32encode(secrets.token_bytes(20)).decode()
            pending[hashlib.sha256(ticket.encode()).hexdigest()] = (secret,time.monotonic())
            return {'ticket':ticket,'authenticator_key':secret,'email':'leo@etexpous.com'}

    @app.post('/setup/finish')
    def finish(data: Finish, request: Request):
        with lock:
            guard(request)
            record = pending.get(hashlib.sha256(data.ticket.encode()).hexdigest())
            if not record or time.monotonic()-record[1]>600:
                raise HTTPException(403,'Setup expired; begin again')
            if data.password != data.repeat_password or len(data.password.encode())>72:
                raise HTTPException(400,'Passwords must match and contain 16+ characters, at most 72 UTF-8 bytes')
            from app.core.cloud_auth import valid_counter
            counter = valid_counter(record[0],data.code)
            if counter is None:
                raise HTTPException(400,'Authenticator code rejected')
            from scripts.provision_cloud_owner import enroll
            try:
                result = enroll(runtime.parent/'marketing.db','leo@etexpous.com',data.password,record[0],counter,runtime)
            except Exception:
                raise HTTPException(409,'Setup not completed; administrator must check state before retrying') from None
            pending.clear()
            return {'status':'OWNER_SETUP_COMPLETE','owner_id':result['owner_id'],'restart_required':True}

    return app
