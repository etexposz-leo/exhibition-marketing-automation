"""Revocable assistant grants. Editorial tools only; no publication transport.

Grant hashes, audit entries and idempotency receipts use the existing encrypted
credential store. A SQLite write reservation serializes revocation and tool calls.
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.channel_workspace import origin
from app.core.credentials import CredentialStore
from app.core.database import get_db
from app.core.module_access import primary_owner, profile, require
from app.core.ownership import authenticated_session
from app.core.security import utcnow
from app.models.models import Campaign, CredentialMetadata, SalesBrief, SalesCopy, User
from app.services import sales_copy as engine, sales_copy_store as copies
from app.services.publishing import owned

owner_router = APIRouter(prefix='/marketing/agent-grants', tags=['Assistant grants'],
                         dependencies=[Depends(authenticated_session)])
tool_router = APIRouter(prefix='/marketing/agent-tools', tags=['Assistant tools'])
SCOPES = {'marketing:read', 'drafts:write', 'review:submit'}
TOOL_SCOPES = {'capabilities': 'marketing:read', 'campaigns': 'marketing:read',
               'drafts': 'marketing:read', 'create_draft': 'drafts:write', 'submit_review': 'review:submit'}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class GrantInput(Strict):
    assistant: Literal['ChatGPT', 'Dot', 'Muse', 'Other']
    scopes: list[Literal['marketing:read', 'drafts:write', 'review:submit']] = Field(min_length=1, max_length=3)
    expires_hours: int = Field(default=24, ge=1, le=720)


class ToolInput(Strict):
    tool: Literal['capabilities', 'campaigns', 'drafts', 'create_draft', 'submit_review']
    campaign_id: int | None = Field(default=None, gt=0)
    copy_id: int | None = Field(default=None, gt=0)
    after_id: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    platform: Literal['linkedin', 'facebook', 'instagram', 'x', 'google_business', 'website'] = 'linkedin'
    topic: str = Field(default='', max_length=2000)
    audience: str = Field(default='', max_length=1000)
    content: str = Field(default='', max_length=30000)
    fingerprint: str = Field(default='', max_length=64)
    idempotency_key: str = Field(default='', max_length=128)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def read(db, owner, scope, default=None):
    try:
        return json.loads(CredentialStore().get(db, owner, scope, 'record'))
    except ValueError:
        return default


def write(db, owner, scope, value):
    CredentialStore().put(db, owner, scope, 'record', json.dumps(value))


def reserve(db):
    if db.bind.dialect.name != 'sqlite':
        raise HTTPException(503, 'Assistant access currently requires the validated SQLite transaction backend')
    if not db.in_transaction():
        db.execute(text('BEGIN IMMEDIATE'))


def check_owner(db):
    who = require(db, 'MARKETING_ACCESS')
    user = db.query(User).filter_by(id=who, is_active=True, is_demo=False).first()
    if who != primary_owner() or not user:
        raise HTTPException(403, 'Active non-demo primary Owner required')
    return who


def public_grant(value):
    return {k: value[k] for k in ('id', 'assistant', 'scopes', 'expires_at', 'revoked', 'created_at')}


@owner_router.get('')
def grants(response: Response, db: Session = Depends(get_db)):
    who = check_owner(db)
    response.headers['Cache-Control'] = 'no-store'
    rows = db.query(CredentialMetadata).filter_by(user_id=who, kind='record').filter(
        CredentialMetadata.scope.like('agent-grant:%')).all()
    values = [read(db, who, r.scope) for r in rows]
    return dict(grants=[public_grant(v) for v in values if v], scopes=sorted(SCOPES),
                connection_status='OWNER_CONNECTION_NOT_VERIFIED', publish_available=False)


@owner_router.post('')
def issue(body: GrantInput, request: Request, response: Response, db: Session = Depends(get_db)):
    origin(request)
    who = check_owner(db)
    ident = secrets.token_hex(16)
    token = ident + '.' + secrets.token_urlsafe(32)
    value = dict(id=ident, assistant=body.assistant, scopes=sorted(set(body.scopes)),
                 token_hash=digest(token), created_at=utcnow().isoformat(),
                 expires_at=(utcnow() + timedelta(hours=body.expires_hours)).isoformat(), revoked=False)
    write(db, who, 'agent-grant:' + ident, value)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return dict(grant=public_grant(value), token=token, show_once=True)


@owner_router.post('/{ident}/revoke')
def revoke(ident: str, request: Request, db: Session = Depends(get_db)):
    origin(request)
    who = check_owner(db)
    # Acquire a write reservation before reading the current grant. Authentication
    # has already begun a read transaction, so end that read-only transaction first.
    db.rollback()
    reserve(db)
    check_owner(db)
    value = read(db, who, 'agent-grant:' + ident)
    if not value:
        raise HTTPException(404, 'Grant not found')
    value['revoked'] = True
    write(db, who, 'agent-grant:' + ident, value)
    db.commit()
    return dict(revoked=True)


@owner_router.get('/{ident}/audit')
def audit(ident: str, response: Response, db: Session = Depends(get_db)):
    who = check_owner(db)
    response.headers['Cache-Control'] = 'no-store'
    if not read(db, who, 'agent-grant:' + ident):
        raise HTTPException(404, 'Grant not found')
    return dict(events=read(db, who, 'agent-audit:' + ident, []), retained_events=200)


def agent_session(request: Request, db: Session = Depends(get_db)):
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 256:
        raise HTTPException(401, 'Assistant grant required')
    token = header[7:]
    ident = token.partition('.')[0]
    if len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
        raise HTTPException(401, 'Invalid assistant grant')
    reserve(db)
    meta = db.query(CredentialMetadata).filter_by(scope='agent-grant:' + ident, kind='record').first()
    if meta is None:
        raise HTTPException(401, 'Invalid assistant grant')
    db.info['owner_id'] = meta.user_id
    value = read(db, meta.user_id, meta.scope)
    if not value or not hmac.compare_digest(value['token_hash'], digest(token)):
        raise HTTPException(401, 'Invalid assistant grant')
    if value['revoked'] or value['expires_at'] <= utcnow().isoformat():
        raise HTTPException(401, 'Assistant grant expired or revoked')
    check_owner(db)
    window = int(time.time() // 60)
    count = value.get('request_count', 0) if value.get('window') == window else 0
    if count >= 60:
        raise HTTPException(429, 'Assistant rate limit: 60 calls per minute')
    value.update(window=window, request_count=count + 1)
    # Persist the counter for rejected requests as well, then reacquire the lock
    # and recheck revocation before the operation (no cached authorization).
    write(db, meta.user_id, meta.scope, value)
    db.commit()
    reserve(db)
    value = read(db, meta.user_id, meta.scope)
    if value['revoked'] or value['expires_at'] <= utcnow().isoformat():
        raise HTTPException(401, 'Assistant grant expired or revoked')
    check_owner(db)
    return value


def perform(body, db, who, grant):
    if body.tool == 'capabilities':
        return dict(tools=[k for k, scope in TOOL_SCOPES.items() if scope in grant['scopes']],
                    drafting_platforms=list(engine.PLATFORMS), publishing=False, approval=False,
                    scheduling=False, outreach=False, data_is_untrusted=True)
    if body.tool == 'campaigns':
        rows = db.query(Campaign).filter(Campaign.id > body.after_id).order_by(Campaign.id).limit(body.limit).all()
        return dict(campaigns=[dict(id=r.id, name=r.campaign_name or r.exhibition_name,
                                   industry=r.customer_industry) for r in rows])
    if body.tool in {'drafts', 'create_draft'}:
        if not body.campaign_id:
            raise HTTPException(422, 'campaign_id required')
        campaign = owned(db, Campaign, body.campaign_id, who)
    if body.tool == 'drafts':
        rows = db.query(SalesCopy).filter_by(campaign_id=campaign.id).filter(SalesCopy.id > body.after_id).order_by(SalesCopy.id).limit(body.limit).all()
        return dict(copies=[copies.view(row) for row in rows], data_is_untrusted=True)
    if body.tool == 'create_draft':
        if not body.content.strip() or not body.topic.strip() or not body.audience.strip():
            raise HTTPException(422, 'content, topic and audience required')
        # An assistant cannot assert owner-confirmed facts or media permissions.
        brief = engine.analyze(engine.Brief(topic=body.topic, target_audience=body.audience,
                                           industry=campaign.customer_industry, trade_show=campaign.exhibition_name))
        row = SalesBrief(user_id=who, campaign_id=campaign.id, payload=json.dumps(brief))
        db.add(row)
        db.flush()
        copy = copies.create_copy(db, row, body.platform, body.content, 'assistant_draft')
        return dict(copy=copies.view(copy), published=False, human_review_required=True)
    if not body.copy_id:
        raise HTTPException(422, 'copy_id required')
    row = owned(db, SalesCopy, body.copy_id, who)
    if body.fingerprint != row.fingerprint or row.status not in {'DRAFT', 'PENDING_REVIEW'}:
        raise HTTPException(409, 'Only the current draft can be submitted for review')
    row.status = 'PENDING_REVIEW'
    return dict(copy_id=row.id, status=row.status, approved=False, published=False)


@tool_router.post('/call')
def call(body: ToolInput, response: Response, grant=Depends(agent_session), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    who = db.info['owner_id']
    if TOOL_SCOPES[body.tool] not in grant['scopes']:
        raise HTTPException(403, 'Tool scope not granted')
    mutation = body.tool in {'create_draft', 'submit_review'}
    receipt = 'agent-receipt:' + grant['id'] + ':' + digest(body.idempotency_key)
    fingerprint = digest(body.model_dump_json())
    if mutation:
        if not body.idempotency_key.strip():
            raise HTTPException(422, 'A stable idempotency_key is required for writes')
        previous = read(db, who, receipt)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Idempotency key was used with different input')
            return dict(**previous['result'], replayed=True)
    result = perform(body, db, who, grant)
    if mutation:
        write(db, who, receipt, dict(fingerprint=fingerprint, result=result))
    events = read(db, who, 'agent-audit:' + grant['id'], [])
    events.append(dict(at=utcnow().isoformat(), tool=body.tool, outcome='SUCCEEDED',
                       campaign_id=body.campaign_id, copy_id=result.get('copy_id', result.get('copy', {}).get('id'))))
    write(db, who, 'agent-audit:' + grant['id'], events[-200:])
    db.commit()
    return dict(**result, replayed=False)
