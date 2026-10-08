"""Internal editorial APIs. These routes never call a publishing adapter."""
import asyncio
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.module_access import require, profile
from app.models.models import Campaign, SalesBrief, SalesCopy, OptimizedContent
from app.api.channel_workspace import origin, asset
from app.services.publishing import owned
from app.services import sales_copy as engine, sales_copy_store as store

router = APIRouter(prefix='/marketing/sales-copy', tags=['Sales Copy Engine'])

def owner(db, write=False):
    ident = require(db, 'MARKETING_ACCESS')
    if write and profile(db, ident)['role'] not in {'OWNER', 'ADMIN', 'STAFF', 'REVIEWER'}:
        raise HTTPException(403, 'Read-only user cannot modify sales copy')
    return ident

class BriefInput(BaseModel):
    campaign_id: int
    brief: engine.Brief

class Generate(BaseModel):
    brief_id: int
    platforms: list[Literal['linkedin','facebook','instagram','x','google_business','website']] = Field(min_length=1, max_length=6)
    mode: Literal['local', 'ai'] = 'local'

class Edit(BaseModel):
    fingerprint: str
    content: str = Field(min_length=1, max_length=30000)

class Decision(BaseModel):
    fingerprint: str
    action: Literal['approve', 'reject']
    acknowledge_warnings: bool = False
    facts_reviewed: bool = False
    media_reviewed: bool = False
    note: str = Field(default='', max_length=3000)

@router.get('/options')
def options(db: Session = Depends(get_db)):
    owner(db)
    return dict(platforms=engine.PLATFORMS, stages=engine.STAGES, content_types=engine.CONTENT_TYPES,
        cta_types=['auto', *engine.CTAS], real_publish_enabled=False, auto_publish=False,
        analytics_contract=['GA4', 'Google Ads', 'LinkedIn', 'Meta', 'Google Business', 'conversion'],
        analytics_connected=False,analytics_fields=['campaign_id','copy_id','platform','source','period_start','period_end','impressions','clicks','engagements','conversions','hook','pain_points','cta','content_type'])

@router.get('/campaigns/{ident}')
def campaign(ident: int, db: Session = Depends(get_db)):
    who = owner(db); owned(db, Campaign, ident, who)
    briefs = db.query(SalesBrief).filter_by(user_id=who, campaign_id=ident).order_by(SalesBrief.id.desc()).all()
    copies = db.query(SalesCopy).filter_by(user_id=who, campaign_id=ident).order_by(SalesCopy.id.desc()).all()
    from app.models.models import ScheduledPost
    latest=json.loads(briefs[0].payload) if briefs else {}
    return dict(briefs=[dict(id=b.id, brief=json.loads(b.payload)) for b in briefs], copies=[store.view(r) for r in copies],
        memory=dict(source_references=[s for b in briefs for s in json.loads(b.payload).get('sources', [])],
                    audience=latest.get('target_audience'),pain_points=latest.get('pain_points',[]),
                    key_messages=[latest.get('main_selling_point'),*latest.get('supporting_selling_points',[])],
                    images=latest.get('asset_ids',[]),cta=latest.get('cta'),keywords=[latest.get('primary_keyword'),*latest.get('secondary_keywords',[])],
                    landing_page=latest.get('website',{}).get('canonical'),
                    published_posts=[dict(id=p.id,platform=p.platform,url=p.url) for p in db.query(ScheduledPost).filter_by(user_id=who,campaign_id=ident,status='published').all()],
                    performance=[], auto_optimization=False))

@router.post('/briefs')
def brief(body: BriefInput, request: Request, db: Session = Depends(get_db)):
    origin(request); who = owner(db, True); owned(db, Campaign, body.campaign_id, who)
    for ident in body.brief.asset_ids: asset(db, ident)
    try: b = engine.analyze(body.brief)
    except ValueError as exc: raise HTTPException(422, str(exc)) from None
    if any(s.confirmed for s in body.brief.sources) and profile(db, who)['role'] not in {'OWNER', 'ADMIN'}:
        raise HTTPException(403, 'Only Owner/Admin may attest source facts')
    row = SalesBrief(user_id=who, campaign_id=body.campaign_id, payload=json.dumps(b, ensure_ascii=False))
    db.add(row); db.commit()
    return dict(id=row.id, brief=b)

@router.post('/generate')
async def generate(body: Generate, request: Request, db: Session = Depends(get_db)):
    origin(request); who = owner(db, True); brief = owned(db, SalesBrief, body.brief_id, who)
    b = json.loads(brief.payload)
    if 'website' in body.platforms:
        b=engine.website_proposal(b)
        # New immutable Brief snapshot, shared by all requested versions.
        brief=SalesBrief(user_id=who,campaign_id=brief.campaign_id,payload=json.dumps(b,ensure_ascii=False))
        db.add(brief);db.flush()
    texts = []
    service = None
    if body.mode == 'ai':
        from app.api.content_inspiration import configured_ai
        service = configured_ai(db)
        if not service.is_available(): raise HTTPException(503, 'AI is not configured; select explicit local drafting mode')
    try:
        for platform in dict.fromkeys(body.platforms):
            text = (await asyncio.wait_for(service.generate_content(engine.ai_prompt(b, platform),
                provider=service.get_provider_name(), max_tokens=2200,
                temperature={'low':.2,'medium':.5,'high':.8}[b['creativity']]), timeout=45)) if service else engine.generate_local(b, platform)
            if not isinstance(text, str) or not text.strip() or len(text) > 30000:
                raise HTTPException(502, 'Invalid AI draft; no copy was stored')
            texts.append((platform, text))
    except asyncio.TimeoutError:
        raise HTTPException(504, 'AI generation timed out; no partial copy was stored') from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'AI generation failed; no provider details or secrets are displayed') from None
    finally:
        from app.services.ai_service import ai_service
        if service is not None and service is not ai_service:
            for client in (service.openai_client, service.deepseek_client):
                if client is not None: await client.close()
    rows = [store.create_copy(db, brief, p, t, body.mode) for p,t in texts]
    db.commit()
    return dict(copies=[store.view(r) for r in rows], published=False)

@router.post('/copies/{ident}/edit')
def edit(ident: int, body: Edit, request: Request, db: Session = Depends(get_db)):
    origin(request); who = owner(db, True); old = owned(db, SalesCopy, ident, who)
    if old.fingerprint != body.fingerprint or old.status == 'SUPERSEDED': raise HTTPException(409, 'Stale draft')
    brief = owned(db, SalesBrief, old.brief_id, who)
    row = store.create_copy(db, brief, old.platform, body.content, 'human_edit', old.original_content)
    store.originality_guard(db,row,old.optimized_content_id)
    old.status = 'SUPERSEDED'
    db.commit(); return store.view(row)

@router.post('/copies/{ident}/review')
def review(ident: int, body: Decision, request: Request, db: Session = Depends(get_db)):
    origin(request); who = owner(db, True); row = owned(db, SalesCopy, ident, who)
    if body.action == 'approve' and row.platform == 'instagram':
        b = json.loads(owned(db, SalesBrief, row.brief_id, who).payload)
        if not b.get('asset_ids') or not body.media_reviewed:
            raise HTTPException(409, 'Instagram requires owner-reviewed media')
        for ident in b['asset_ids']: asset(db, ident)
    store.decide(db, row, body.fingerprint, body.action, body.acknowledge_warnings, body.facts_reviewed, body.note)
    # Feed existing workbench queue without invoking its publication transport.
    if row.optimized_content_id:
        from app.api.unified_marketing import save_record, load_record
        key = 'unified-review:' + str(row.optimized_content_id)
        record = load_record(db, key, default={'history':[]})
        record['status'] = 'READY_TO_PUBLISH' if row.status == 'APPROVED' else 'REJECTED'
        record['history'].append(json.loads(row.review_log)[-1])
        save_record(db, key, record)
    else: db.commit()
    return dict(copy=store.view(row), external_action=False)

@router.post('/import-draft/{ident}')
def import_draft(ident: int, body: Generate, request: Request, db: Session = Depends(get_db)):
    origin(request); who = owner(db, True)
    old = owned(db, OptimizedContent, ident, who); brief = owned(db, SalesBrief, body.brief_id, who)
    if old.campaign_id != brief.campaign_id or old.platform not in engine.PLATFORMS:
        raise HTTPException(409, 'Campaign/platform mismatch')
    row = store.create_copy(db, brief, old.platform, old.optimized_content, 'legacy_import', old.original_content)
    store.originality_guard(db,row,old.id)
    db.commit(); return store.view(row)

@router.get('/copies/{ident}/export')
def export(ident: int, db: Session = Depends(get_db)):
    who = owner(db); row = owned(db, SalesCopy, ident, who)
    brief = owned(db, SalesBrief, row.brief_id, who)
    return dict(copy=store.view(row), brief=json.loads(brief.payload), deployment='NONE',
        publishable=row.status == 'APPROVED' and not any(c['status']=='NEEDS_REVIEW' for c in json.loads(row.evaluation)['claims']), website_live_checks='NOT_PERFORMED')
