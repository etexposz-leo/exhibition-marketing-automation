"""Versioned editorial records and the final fail-closed REAL delivery guard."""
import json
from fastapi import HTTPException
from app.models.models import SalesBrief, SalesCopy, OptimizedContent, ScheduledPost
from app.services import sales_copy as engine
from app.core.security import utcnow

def history(db, owner, exclude=None):
    rows = [dict(id=r.id, platform=r.platform, content=r.content, kind='sales_copy')
        for r in db.query(SalesCopy).filter_by(user_id=owner).order_by(SalesCopy.id.desc()).limit(500).all() if r.id != exclude]
    rows += [dict(id=r.id, platform=r.platform, content=r.content, kind='published')
        for r in db.query(ScheduledPost).filter_by(user_id=owner, status='published').order_by(ScheduledPost.id.desc()).limit(500).all()]
    return rows

def create_copy(db, brief, platform, content, mode='local', original=None):
    b = json.loads(brief.payload)
    report = engine.evaluate(content, platform, b, history(db, brief.user_id))
    opt = None
    if platform != 'website':
        opt = OptimizedContent(user_id=brief.user_id, campaign_id=brief.campaign_id, platform=platform,
            original_content=original or content, optimized_content=content,
            changes=json.dumps({'sales_copy': True, 'asset_ids':b.get('asset_ids', []), 'warnings':[]}),
            character_count=len(content), character_limit=engine.LIMITS[platform])
        db.add(opt); db.flush()
    row = SalesCopy(user_id=brief.user_id, campaign_id=brief.campaign_id, brief_id=brief.id,
        optimized_content_id=opt.id if opt else None, platform=platform, content=content,
        original_content=original or content, evaluation=json.dumps(report), fingerprint=report['fingerprint'],
        status='DRAFT', generation_mode=mode, review_log='[]')
    db.add(row); db.flush()
    return row

def attach_existing(db, opt, context=None):
    """Bring manual and inspiration drafts into the same engine before review."""
    from app.models.models import Campaign
    if opt.platform not in engine.PLATFORMS:return None
    campaign=db.query(Campaign).filter_by(id=opt.campaign_id,user_id=opt.user_id).one()
    last=db.query(SalesBrief).filter_by(user_id=opt.user_id,campaign_id=opt.campaign_id).order_by(SalesBrief.id.desc()).first()
    b=context or (json.loads(last.payload) if last else engine.analyze(engine.Brief(
        target_audience=campaign.customer_industry+' exhibitors',industry=campaign.customer_industry,
        trade_show=campaign.exhibition_name)))
    b=json.loads(json.dumps(b))
    b['asset_ids']=json.loads(opt.changes or '{}').get('asset_ids',[])
    brief=SalesBrief(user_id=opt.user_id,campaign_id=opt.campaign_id,payload=json.dumps(b))
    db.add(brief);db.flush()
    report=engine.evaluate(opt.optimized_content,opt.platform,b,history(db,opt.user_id))
    row=SalesCopy(user_id=opt.user_id,campaign_id=opt.campaign_id,brief_id=brief.id,optimized_content_id=opt.id,
        platform=opt.platform,content=opt.optimized_content,original_content=opt.original_content or opt.optimized_content,
        evaluation=json.dumps(report),fingerprint=report['fingerprint'],status='DRAFT',generation_mode='manual_or_inspiration',review_log='[]')
    db.add(row);db.flush()
    return row

def view(row):
    return dict(id=row.id, brief_id=row.brief_id, campaign_id=row.campaign_id,
        content_id=row.optimized_content_id, platform=row.platform, content=row.content,
        original_content=row.original_content, gate=json.loads(row.evaluation), fingerprint=row.fingerprint,
        status=row.status, mode=row.generation_mode, review_log=json.loads(row.review_log))

def originality_guard(db, row, source_content_id=None):
    from app.core.credentials import CredentialStore
    from app.services.original_copy import overlap
    scope='originality:'+str(source_content_id or row.optimized_content_id)
    try: value=json.loads(CredentialStore().get(db,row.user_id,scope,'record'))
    except ValueError:return
    if overlap(value['source_excerpt'],row.content)['status']=='HIGH_OVERLAP':
        raise HTTPException(409,'Original reference overlap too high; rewrite before review')
    if source_content_id and row.optimized_content_id:
        CredentialStore().put(db,row.user_id,'originality:'+str(row.optimized_content_id),'record',json.dumps(value))

def decide(db, row, fingerprint, action, acknowledge=False, facts_reviewed=False, note=''):
    from app.core.module_access import profile
    if profile(db, row.user_id)['role'] not in {'OWNER', 'ADMIN'}:
        raise HTTPException(403, 'Owner/Admin editorial review required')
    if fingerprint != row.fingerprint:
        raise HTTPException(409, 'Copy changed; review the latest version')
    if row.status == 'SUPERSEDED':
        raise HTTPException(409, 'Copy superseded; review the new version')
    brief = db.query(SalesBrief).filter_by(id=row.brief_id, user_id=row.user_id).one()
    report = engine.evaluate(row.content, row.platform, json.loads(brief.payload), history(db, row.user_id, row.id))
    if action == 'approve':
        originality_guard(db,row)
        if report['status'] == 'FAIL': raise HTTPException(409, 'FAIL cannot be approved; edit and re-evaluate')
        if report['status'] == 'WARN' and (not acknowledge or not note.strip()):
            raise HTTPException(409, 'WARN requires an explicit admin acknowledgement and review note')
        if not facts_reviewed: raise HTTPException(409, 'Confirm facts, sources and preview before approval')
        row.status = 'APPROVED'
    elif action == 'reject': row.status = 'REJECTED'
    else: raise HTTPException(400, 'Unknown editorial decision')
    events = json.loads(row.review_log)
    events.append(dict(action=action, actor=row.user_id, at=utcnow().isoformat(), fingerprint=row.fingerprint,
        warning_acknowledged=acknowledge, facts_reviewed=facts_reviewed, note=note, gate=report))
    row.review_log = json.dumps(events)
    row.evaluation = json.dumps(report)
    return row

def require_approved(db, owner, content_id, platform, content, campaign_id):
    row = db.query(SalesCopy).filter_by(user_id=owner, optimized_content_id=content_id,
        platform=platform, campaign_id=campaign_id, status='APPROVED').order_by(SalesCopy.id.desc()).first() if content_id else None
    if row is None or row.content != content:
        raise HTTPException(409, 'Sales Copy Engine: this exact version needs human approval')
    current=db.query(OptimizedContent).filter_by(id=content_id,user_id=owner).first()
    if not current or current.optimized_content != content:
        raise HTTPException(409,'Approved content was modified; review again')
    originality_guard(db,row)
    brief = db.query(SalesBrief).filter_by(id=row.brief_id, user_id=owner).one()
    report = engine.evaluate(content, platform, json.loads(brief.payload))
    if report['fingerprint'] != row.fingerprint or report['status'] == 'FAIL':
        raise HTTPException(409, 'Sales Copy quality approval is stale or failed')
    # An acknowledgement permits a reviewed draft; unsupported factual claims
    # remain blocked at actual delivery until evidence is corrected and reviewed.
    if any(c['status'] != 'SUPPORTED' for c in report['claims']):
        raise HTTPException(409, 'Unverified claims cannot be published; supply confirmed evidence')
    return row
