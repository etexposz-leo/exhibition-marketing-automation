"""Authenticated management shell over existing social storage and Backlink service.

No publication/delivery adapter is called by these routes. Shared content is owner-
encrypted in the existing store; Backlink remains authoritative for acquisition state.
"""
import hashlib,json,os
from pathlib import Path
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.credentials import CredentialStore
from app.core.security import utcnow
from app.models.models import Campaign,OptimizedContent,ScheduledPost,CredentialMetadata
from app.api import channel_workspace as channels
from app.services.publishing import owned
from app.services import original_copy

ROOT=Path(__file__).resolve().parents[2]
router=APIRouter(prefix='/marketing',tags=['unified marketing review'])
CONFIG=ROOT/'config/unified-marketing.json'
BACKLINK_BASE='http://127.0.0.1:18422'

def config():
    from app.core.cloud_runtime import enabled, workspace_config
    return workspace_config() if enabled() else json.loads(CONFIG.read_text(encoding='utf-8'))
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def load_record(db,scope,kind='record',default=None):
    try:return json.loads(CredentialStore().get(db,channels.owner(db),scope,kind))
    except ValueError:return default
def save_record(db,scope,value,kind='record'):
    CredentialStore().put(db,channels.owner(db),scope,kind,json.dumps(value,ensure_ascii=False));db.flush() if db.info.get('original_draft_transaction') else db.commit()

def backlink_owner(db):
    if channels.owner(db)!=config()['backlink_owner_id']:raise HTTPException(403,'Backlink workspace belongs to another Owner')

def backlink_call(method='GET',payload=None,path='/api/review'):
    try:
        with httpx.Client(base_url=BACKLINK_BASE,trust_env=False,timeout=15) as client:
            response=client.get('/api/review');response.raise_for_status();data=response.json()
            if method=='GET':data.pop('csrf',None);return data
            r=client.post(path,json=payload,headers={'Origin':BACKLINK_BASE,'X-Review-CSRF':data['csrf']})
            if r.status_code>=400:raise HTTPException(r.status_code,r.json().get('error','Review failed'))
            return r.json()
    except httpx.HTTPError:raise HTTPException(503,'Backlink review service unavailable; start its packaged local launcher') from None

def social_rows(db):
    rows=[];seen=set()
    for row in db.query(OptimizedContent).filter_by(user_id=channels.owner(db)).order_by(OptimizedContent.id.desc()).all():
        key=(row.campaign_id,row.platform)
        if key in seen:continue
        seen.add(key)
        try:p=json.loads(row.changes or '{}')
        except ValueError:p={}
        if not isinstance(p,dict):p={}
        review=load_record(db,'unified-review:'+str(row.id),default={})
        payload={'id':row.id,'campaign_id':row.campaign_id,'platform':row.platform,'caption':row.optimized_content,
            'title':p.get('title',''),'asset_ids':p.get('asset_ids',[]),'notes':review.get('notes',''),
            'warnings':p.get('warnings',[]),'recommended_publish_time':p.get('recommended_publish_time'),
            'status':review.get('status','DRAFT'),'changes_fingerprint':p.get('fingerprint')}
        payload['revision']=fingerprint(payload);rows.append(payload)
        from app.models.models import SalesCopy
        sales=db.query(SalesCopy).filter_by(user_id=channels.owner(db),optimized_content_id=row.id).first()
        if sales:
            payload['sales_copy_id']=sales.id
            payload['sales_gate']=json.loads(sales.evaluation)
        guard=load_record(db,'originality:'+str(row.id),default={})
        if guard:
            payload['originality_parent_id']=row.id
            payload['originality']=original_copy.overlap(guard['source_excerpt'],row.optimized_content)
            payload['source_url']=guard['source_url']
            if payload['originality']['status']=='HIGH_OVERLAP':payload['warnings'].append('与参考摘要重合过高，必须重写')
            payload['revision']=fingerprint({k:v for k,v in payload.items() if k!='revision'})
    return rows

@router.get('/state')
def state(db:Session=Depends(get_db)):
    backlink_owner(db)
    try:backlinks=backlink_call();error=None
    except HTTPException as exc:backlinks={'items':[],'opportunities':[],'responses':[],'links':[],'suppression':[],'analytics':{}};error=exc.detail
    context={str(c.id):load_record(db,'campaign-context:'+str(c.id),default={}) for c in db.query(Campaign).filter_by(user_id=channels.owner(db)).all()}
    assets=[]
    for row in db.query(CredentialMetadata).filter(CredentialMetadata.user_id==channels.owner(db),CredentialMetadata.scope.like('channel-asset:%'),CredentialMetadata.kind=='media').all():
        ident=row.scope.split(':',1)[1];asset=channels.asset(db,ident)
        assets.append({'id':ident,'name':asset['name'],'mime':asset['mime'],'bytes':asset['bytes'],'url':'/api/channels/media/'+ident})
    calendar=[{'id':p.id,'campaign_id':p.campaign_id,'platform':p.platform,'status':p.status,'scheduled_at':str(p.scheduled_at) if p.scheduled_at else None,'published_at':str(p.published_at) if p.published_at else None,'url':p.url} for p in db.query(ScheduledPost).filter_by(user_id=channels.owner(db)).all()]
    return {'campaigns':channels.campaigns(db),'campaign_context':context,'social':social_rows(db),'channels':channels.overview(db)['channels'],
        'backlinks':backlinks,'backlink_error':error,'assets':assets,'calendar':calendar,
        'company':load_record(db,'shared-company',default={'company_name':'ET EXPO INC','website':'https://etexpous.com/','description':'','services':'','case_studies':'','approved_boilerplate':'','logo_asset_id':'','notes':''}),
        'controls':{'REAL_SOCIAL_PUBLISH_ENABLED':False,'AUTO_EMAIL_SEND_ENABLED':False,'AUTO_DIRECTORY_SUBMIT_ENABLED':False,'AUTO_FOLLOWUP_ENABLED':False}}

@router.get('/backlinks/review')
def backlinks(db:Session=Depends(get_db)):
    backlink_owner(db);return backlink_call()

@router.get('/backlinks/opportunities')
def opportunity_manager(db:Session=Depends(get_db)):
    backlink_owner(db)
    return backlink_call('POST',{'action':'list'},'/api/opportunity-manager')

@router.get('/backlinks/opportunities.csv')
def opportunity_csv(db:Session=Depends(get_db)):
    backlink_owner(db)
    value=backlink_call('POST',{'action':'csv'},'/api/opportunity-manager')
    return Response('\ufeff'+value['csv'],media_type='text/csv',headers={'Content-Disposition':'attachment; filename="backlink-opportunities.csv"','Cache-Control':'no-store'})

@router.post('/backlinks/opportunities')
def opportunity_action(body:dict,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);backlink_owner(db)
    if len(json.dumps(body))>50000:raise HTTPException(413,'Request too large')
    return backlink_call('POST',body,'/api/opportunity-manager')

class Decision(BaseModel):
    target:str='backlink'
    id:str
    revision:str
    action:str
    fields:dict=Field(default_factory=dict)
    media_reviewed:bool=False
    facts_reviewed:bool=False
    acknowledge_warnings:bool=False
    review_note:str=Field(default='',max_length=3000)

@router.post('/review')
@router.post('/backlinks/review')
def review(body:Decision,request:Request,db:Session=Depends(get_db)):
    channels.origin(request)
    if body.target=='backlink':
        backlink_owner(db)
        if body.action=='campaign':
            owned(db,Campaign,int(body.fields.get('campaign_id',0)),channels.owner(db))
            body.fields={'campaign_id':int(body.fields['campaign_id']),'marketing_owner_id':channels.owner(db)}
        return backlink_call('POST',body.model_dump())
    if body.target!='social':raise HTTPException(400,'Unknown review target')
    row=owned(db,OptimizedContent,int(body.id),channels.owner(db))
    current=next((x for x in social_rows(db) if x['id']==row.id),None)
    if not current or current['revision']!=body.revision:raise HTTPException(409,'Draft changed; review latest content')
    record=load_record(db,'unified-review:'+str(row.id),default={'history':[]})
    if body.action=='approve':
        if current.get('originality') and not body.facts_reviewed:raise HTTPException(400,'原创草稿需再次确认事实和来源归属')
        if current['status']=='READY_TO_PUBLISH':raise HTTPException(409,'This exact version is already approved')
        if current['warnings']:raise HTTPException(400,'Resolve content/media warnings first')
        from app.services.sales_copy import PLATFORMS
        if current['platform'] in PLATFORMS:
            from app.models.models import SalesCopy
            from app.services.sales_copy_store import decide
            sales=db.query(SalesCopy).filter_by(user_id=channels.owner(db),optimized_content_id=row.id).first()
            if not sales:raise HTTPException(409,'请先在 Sales Copy Engine 导入此草稿、确认 Sales Brief 并完成质量审核')
            decide(db,sales,sales.fingerprint,'approve',body.acknowledge_warnings,body.facts_reviewed,body.review_note)
        if current['platform'] in channels.NEW_CHANNELS:
            channels.approve(row.id,channels.Approval(fingerprint=current['changes_fingerprint'],media_reviewed=body.media_reviewed),request,db)
        elif current['platform']=='instagram' and (not current['asset_ids'] or not body.media_reviewed):raise HTTPException(400,'Instagram requires an Owner-reviewed media asset')
        record['status']='READY_TO_PUBLISH'
    elif body.action in {'reject','skip'}:
        from app.models.models import SalesCopy
        sales=db.query(SalesCopy).filter_by(user_id=channels.owner(db),optimized_content_id=row.id).first()
        if sales:sales.status='REJECTED'
        record['status']='REJECTED' if body.action=='reject' else 'DRAFT'
        if row.platform in channels.NEW_CHANNELS:CredentialStore().put(db,channels.owner(db),f'channel-draft:{row.id}','approval',json.dumps({'fingerprint':'REVOKED_BY_OWNER_REVIEW'}))
    else:raise HTTPException(400,'Use versioned social draft editor to edit')
    record['history'].append({'action':body.action,'at':utcnow().isoformat(),'revision':body.revision})
    save_record(db,'unified-review:'+str(row.id),record)
    return {'status':record['status'],'external_action':False}

class SharedCompany(BaseModel):
    company_name:str=Field(default='ET EXPO INC',max_length=300)
    website:str=Field(default='https://etexpous.com/',max_length=1000)
    description:str=Field(default='',max_length=10000)
    services:str=Field(default='',max_length=10000)
    case_studies:str=Field(default='',max_length=10000)
    approved_boilerplate:str=Field(default='',max_length=10000)
    logo_asset_id:str=Field(default='',max_length=100)
    notes:str=Field(default='',max_length=10000)

@router.get('/company')
def get_company(db:Session=Depends(get_db)):
    return load_record(db,'shared-company',default=SharedCompany().model_dump())

@router.post('/dr/recovery-key')
def download_recovery_key(request:Request,db:Session=Depends(get_db)):
    channels.origin(request);backlink_owner(db)
    from scripts.acceptance_local import PRIVATE,protect
    path=PRIVATE/'unified-dr-recovery.dpapi'
    if not path.exists():raise HTTPException(409,'Build the complete DR package first')
    key=protect(path.read_bytes(),decrypt=True)
    save_record(db,'dr-recovery-export',{'downloaded_at':utcnow().isoformat(),'owner':channels.owner(db),'key_id':hashlib.sha256(key).hexdigest()[:16]})
    return Response(key+b'\n',media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="ETEXPO-unified-DR-recovery-key.txt"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'})

@router.post('/company')
def company(body:SharedCompany,request:Request,db:Session=Depends(get_db)):
    channels.origin(request)
    if body.logo_asset_id:channels.asset(db,body.logo_asset_id)
    value=body.model_dump();value['updated_at']=utcnow().isoformat();save_record(db,'shared-company',value)
    return {'saved':True}

class Context(BaseModel):
    notes:str=Field(default='',max_length=10000)
    asset_ids:list[str]=Field(default_factory=list,max_length=30)

class OpportunityLink(BaseModel):
    id:str
    campaign_id:int

@router.post('/opportunity-campaign')
def opportunity_campaign(body:OpportunityLink,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);backlink_owner(db);owned(db,Campaign,body.campaign_id,channels.owner(db))
    return backlink_call('POST',{'id':body.id,'campaign_id':body.campaign_id,'marketing_owner_id':channels.owner(db)},'/api/opportunity')

@router.post('/campaigns/{ident}/context')
def campaign_context(ident:int,body:Context,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);owned(db,Campaign,ident,channels.owner(db))
    for a in body.asset_ids:channels.asset(db,a)
    save_record(db,'campaign-context:'+str(ident),body.model_dump());return {'saved':True}

class SocialDraft(channels.Variant):
    campaign_id:int
    platform:str
    originality_parent_id:int|None=None

@router.post('/social-drafts')
def social_draft(body:SocialDraft,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);owned(db,Campaign,body.campaign_id,channels.owner(db))
    from app.services.sales_copy import PLATFORMS
    if body.platform not in set(channels.CHANNELS)|set(PLATFORMS)-{'website'}:raise HTTPException(400,'Unknown channel')
    guard=None
    if body.originality_parent_id:
        owned(db,OptimizedContent,body.originality_parent_id,channels.owner(db))
        guard=load_record(db,'originality:'+str(body.originality_parent_id))
        if not guard:raise HTTPException(404,'原文溯源记录不存在')
    def attach(result):
        if guard:
            value={**guard,'facts_reviewed':False,'check':original_copy.overlap(guard['source_excerpt'],body.caption)}
            save_record(db,'originality:'+str(result['id']),value)
        return result
    variant=channels.Variant(**body.model_dump(exclude={'campaign_id','platform','originality_parent_id'}))
    if body.platform in channels.NEW_CHANNELS:return attach(channels.save(body.campaign_id,body.platform,variant,request,db))
    for a in body.asset_ids:channels.asset(db,a)
    if body.cover_id:channels.asset(db,body.cover_id)
    if body.recommended_publish_time:
        try:channels.utc_time(body.recommended_publish_time)
        except ValueError:raise HTTPException(400,'Timezone required') from None
    value=variant.model_dump();value['warnings']=[] if body.platform!='instagram' or body.asset_ids else ['Instagram media required before approval']
    value['fingerprint']=fingerprint(value);value['status']='DRAFT'
    row=OptimizedContent(user_id=channels.owner(db),campaign_id=body.campaign_id,platform=body.platform,original_content=body.caption,optimized_content=body.caption,changes=json.dumps(value),warnings=json.dumps(value['warnings']),character_count=len(body.caption))
    db.add(row);db.flush()
    from app.services.sales_copy_store import attach_existing
    sales=attach_existing(db,row,db.info.get('sales_brief_context'))
    db.flush() if db.info.get('original_draft_transaction') else db.commit()
    return attach({'id':row.id,**value, 'sales_copy_id':sales.id if sales else None})
