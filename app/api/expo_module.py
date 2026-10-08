"""Review-only local ExpoCrawler module. No delivery or pricing code."""
import json,threading,time,uuid
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,Request,HTTPException,Response
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import module_access as access
from app.api import unified_marketing as work,exhibitor_leads as leads
from app.api.channel_workspace import origin
from app.services import expo_acquisition as crawl
from app.models.models import Event
router=APIRouter(prefix='/marketing/modules/crawler',tags=['ExpoCrawler'])
LOCK=threading.RLock();SCOPE='expocrawler-v1';ACTIVE=set()
def state(db):return work.load_record(db,SCOPE,default=None) or {'jobs':{},'records':{},'transfers':{},'quote_drafts':{}}
def save(db,s):work.save_record(db,SCOPE,s)
def auth(request,db,permission):origin(request);return access.require(db,permission)
def row(s,table,key):
    if key not in s[table]:raise HTTPException(404,'Record not found')
    return s[table][key]
def revision(r):return crawl.digest(r)
def check(r,v):
    if revision(r)!=v:raise HTTPException(409,'Record changed; refresh and review again')
class Job(BaseModel):
    name:str=Field(min_length=1,max_length=180)
    source_url:str=Field(max_length=2000)
    trade_show:str=Field(default='',max_length=200)
    show_url:str=Field(default='',max_length=2000)
    start_date:str='';end_date:str=''
    venue:str=Field(default='',max_length=200)
    city:str=Field(default='',max_length=100)
    state:str=Field(default='',max_length=100)
    country:str=Field(default='',max_length=100)
    source_type:Literal['OFFICIAL_EXHIBITOR_LIST','OFFICIAL_DIRECTORY','INDUSTRY_DIRECTORY','COMPANY_EVENTS']='OFFICIAL_EXHIBITOR_LIST'
    terms_reviewed:bool=False
    max_pages:int=Field(default=10,ge=1,le=100)

@router.get('')
def listing(db:Session=Depends(get_db)):
    user=access.require(db,'CRAWLER_VIEW');s=state(db)
    from app.services.expo_worker import status as worker_status
    return {**s,'jobs':[{**j,'revision':revision(j),'request_active':(user,j['id']) in ACTIVE} for j in s['jobs'].values()], 'records':[{**r,'revision':revision(r)} for r in s['records'].values()], 'auto_outreach':False,'execution':'SERVICE_BACKGROUND_WORKER','worker':worker_status(),'quote_robot_connected':False}

@router.post('/jobs')
def create(body:Job,request:Request,db:Session=Depends(get_db)):
    auth(request,db,'CRAWLER_CONFIGURE')
    try:
        source=crawl.public.normalize_url(body.source_url)
        if body.show_url:crawl.public.normalize_url(body.show_url)
        for value in (body.start_date,body.end_date):
            if value:date.fromisoformat(value)
        if body.start_date and body.end_date and body.end_date<body.start_date:raise ValueError()
    except ValueError:raise HTTPException(400,'Use public HTTPS URLs and valid ISO date range') from None
    with LOCK:
        s=state(db)
        if len(s['jobs'])>=200:raise HTTPException(409,'Job capacity reached')
        ident=uuid.uuid4().hex;j={**body.model_dump(),'id':ident,'source_url':source,'status':'SAVED','pending':[source],'visited':[],'record_ids':[],'started_at':None,'completed_at':None,'errors':0,'last_error':'','next_request_at':0,'attempts':{},'records_found':0}
        s['jobs'][ident]=j;save(db,s)
    return {'id':ident}

class Action(BaseModel):action:Literal['start','pause','resume','retry','cancel']
@router.post('/jobs/{ident}/action')
def action(ident:str,body:Action,request:Request,db:Session=Depends(get_db)):
    user=auth(request,db,'CRAWLER_RUN')
    with LOCK:
        s=state(db);j=row(s,'jobs',ident)
        allowed={'start':{'SAVED'},'pause':{'RUNNING'},'resume':{'PAUSED'},'retry':{'FAILED','MANUAL_ACTION_REQUIRED'},'cancel':{'SAVED','RUNNING','PAUSED','FAILED','MANUAL_ACTION_REQUIRED'}}
        if j['status'] not in allowed[body.action]:raise HTTPException(409,'Action not valid for current job state')
        if body.action in {'start','resume','retry'}:
            if not j['terms_reviewed']:raise HTTPException(409,'Create a job with source terms reviewed before crawling')
            if (user,ident) in ACTIVE:raise HTTPException(409,'Previous request still finishing')
            j['status']='RUNNING';j['started_at']=j['started_at'] or crawl.now();j['last_error']=''
            if body.action=='retry':j['attempts']={};j['next_request_at']=max(time.time()+30,j['next_request_at'])
        else:j['status']='PAUSED' if body.action=='pause' else 'CANCELLED'
        save(db,s)
    return {'status':j['status']}

@router.post('/jobs/{ident}/step')
def step(ident:str,request:Request,db:Session=Depends(get_db)):
    user=auth(request,db,'CRAWLER_RUN');key=(user,ident)
    with LOCK:
        s=state(db);j=row(s,'jobs',ident)
        if j['status']!='RUNNING':raise HTTPException(409,'Job is not running')
        if key in ACTIVE:raise HTTPException(409,'A request is already active')
        if ACTIVE:raise HTTPException(409,'Another crawler request is active; retry later')
        if time.time()<j['next_request_at']:return {'waiting':True,'next_request_at':j['next_request_at']}
        if not j['pending'] or len(j['visited'])>=j['max_pages']:
            j.update(status='COMPLETED' if j['records_found'] else 'MANUAL_ACTION_REQUIRED',completed_at=crawl.now(),last_error='' if j['records_found'] else 'NO_RECORDS_REVIEW_REQUIRED');save(db,s);return {'status':'COMPLETED'}
        source=j['pending'][0];ACTIVE.add(key);db.rollback()
    result=None;failure=None
    try:
        resolved,html=crawl.fetch(source);result=crawl.normalize(html,resolved,j)
        if not result[0] and not result[1]:raise crawl.Manual('NO_STRUCTURED_RECORDS_REVIEW_SOURCE')
    except crawl.Retry:failure='RETRY_BACKOFF'
    except crawl.Manual as exc:failure=str(exc)
    except (ValueError,OSError):failure='SOURCE_BLOCKED_OR_UNAVAILABLE_REVIEW_REQUIRED'
    except Exception:failure='PARSER_FAILED'
    finally:
        with LOCK:
            try:
                db.expire_all();s=state(db);j=row(s,'jobs',ident)
                from app.models.models import User
                account=db.query(User).filter(User.id==user).first();profile=access.profile(db,user)
                if j['status']=='RUNNING' and (not account or not account.is_active or profile['locked'] or 'CRAWLER_RUN' not in profile['permissions']):
                    j.update(status='PAUSED',last_error='ACCOUNT_OR_CRAWLER_PERMISSION_REVOKED');save(db,s)
                if j['status']=='RUNNING':
                    j['next_request_at']=time.time()+10
                    if failure:
                        j['errors']+=1;j['last_error']=failure;j['attempts'][source]=j['attempts'].get(source,0)+1
                        if failure=='RETRY_BACKOFF' and j['attempts'][source]<3:j['next_request_at']=time.time()+30*2**j['attempts'][source]
                        else:j['status']='FAILED' if failure in {'PARSER_FAILED','RETRY_BACKOFF'} else 'MANUAL_ACTION_REQUIRED'
                    else:
                        records,links=result
                        if len(s['records'])+len(records)>5000:j.update(status='MANUAL_ACTION_REQUIRED',last_error='RECORD_CAPACITY_REACHED')
                        else:
                            crawl.merge(s['records'],records)
                            for r in records:
                                match=next(x for x in s['records'].values() if crawl.keys(x)&crawl.keys(r))
                                if match['id'] not in j['record_ids']:j['record_ids'].append(match['id'])
                            j['visited'].append(source);j['pending'].pop(0)
                            for link in links:
                                if link not in j['visited']+j['pending'] and len(j['visited'])+len(j['pending'])<j['max_pages']:j['pending'].append(link)
                            j['records_found']=len(j['record_ids'])
                            if not j['pending'] or len(j['visited'])>=j['max_pages']:j.update(status='COMPLETED' if j['records_found'] else 'MANUAL_ACTION_REQUIRED',completed_at=crawl.now(),last_error='' if j['records_found'] else 'NO_RECORDS_REVIEW_REQUIRED')
                    save(db,s)
            finally:ACTIVE.discard(key)
    return {'status':j['status'],'last_error':j['last_error']}

class Review(BaseModel):
    revision:str
    action:Literal['approve','reject','edit']
    fields:dict[str,str]=Field(default_factory=dict)
@router.post('/records/{ident}/review')
def review(ident:str,body:Review,request:Request,db:Session=Depends(get_db)):
    user=auth(request,db,'CRAWLER_APPROVE_RESULTS')
    with LOCK:
        s=state(db);r=row(s,'records',ident);check(r,body.revision)
        if body.action=='edit':
            allowed=set(crawl.FIELDS)-{'source_url','source_type','crawled_at','confidence','content_hash'}
            if set(body.fields)-allowed or any(len(v)>2000 for v in body.fields.values()):raise HTTPException(400,'Invalid editable fields')
            for k,v in body.fields.items():
                if v and k in {'company_website','show_url'}:
                    try:crawl.public.normalize_url(v)
                    except ValueError:raise HTTPException(400,'Invalid public URL') from None
                if v and k in {'start_date','end_date'}:
                    try:date.fromisoformat(v)
                    except ValueError:raise HTTPException(400,'Invalid ISO date') from None
            r.update(body.fields);r['status']='PENDING_REVIEW';r['reviewed_by']=None
        else:r.update(status='APPROVED' if body.action=='approve' else 'REJECTED',reviewed_by=user,reviewed_at=crawl.now())
        save(db,s)
    return {'saved':True}

class Transfer(BaseModel):
    revision:str
    target:Literal['leads','calendar','backlinks','quote']
    official_verified:bool=False
    public_business_confirmed:bool=False
    qualified:bool=False
@router.post('/records/{ident}/transfer')
def transfer(ident:str,body:Transfer,request:Request,db:Session=Depends(get_db)):
    user=auth(request,db,'CRAWLER_APPROVE_RESULTS')
    with LOCK:
        s=state(db);r=row(s,'records',ident);check(r,body.revision)
        if r['status']!='APPROVED':raise HTTPException(409,'Approve exact record first')
        token=ident+':'+body.target
        if token in s['transfers']:return {**s['transfers'][token],'duplicate':True}
        if body.target=='leads':
            work.backlink_owner(db)
            if not body.public_business_confirmed:raise HTTPException(409,'Confirm public business provenance')
            try:
                value=leads.Lead(company_name=r['company_name'],company_website=r['company_website'],trade_show=r['trade_show'],trade_show_date=r['start_date'],trade_show_city=r['city'],venue=r['venue'],country=r['country'],booth_number=r['booth_number'],contact_name=r['contact_name'],contact_title=r['contact_title'],business_email=r['business_email'],phone=r['phone'],source_url=r['source_url'],source_type=r['source_type'],source_excerpt=r['source_excerpt'],email_source=r['source_url'] if r['business_email'] else '',email_public_confirmed=False,public_business_only=True,notes='ExpoCrawler reviewed record '+ident+'; email still requires outreach verification')
            except ValueError:raise HTTPException(409,'Complete company, website, show and source evidence before transfer') from None
            result=leads.add_lead(value,request,db)
        elif body.target=='calendar':
            if not body.official_verified or not r['source_type'].startswith('OFFICIAL_'):raise HTTPException(409,'Verified official show source required')
            if not r['trade_show'] or not r['start_date'] or not r['show_url']:raise HTTPException(409,'Show name, official URL and date required')
            try:start=date.fromisoformat(r['start_date']);end=date.fromisoformat(r['end_date']) if r['end_date'] else None
            except ValueError:raise HTTPException(409,'Valid dates required') from None
            if end and end<start:raise HTTPException(409,'End date precedes start date')
            existing=db.query(Event).filter(Event.user_id==user,Event.event_name==r['trade_show'],Event.start_date==start).first()
            if existing:raise HTTPException(409,'Curated event already exists; no overwrite performed')
            event=Event(user_id=user,event_name=r['trade_show'],start_date=start,end_date=end,venue=r['venue'],city=r['city'],country=r['country'],website=r['show_url'],status='active');db.add(event);db.flush();result={'event_id':event.id}
        elif body.target=='backlinks':
            work.backlink_owner(db)
            from app.services.expo_backlink import handoff
            result=handoff(r)
        else:
            if not body.qualified or not r['company_name'] or not r['trade_show'] or token.replace(':quote',':leads') not in s['transfers']:raise HTTPException(409,'Qualified company/show with reviewed lead transfer required')
            draft={'id':ident,'status':'DRAFT_REQUIRES_QUOTE_ROBOT_IMPORT','company':r['company_name'],'trade_show':r['trade_show'],'booth_number':r['booth_number'],'source_url':r['source_url'],'lead_id':s['transfers'][ident+':leads']['id'],'pricing':None,'quote_robot_received':False}
            s['quote_drafts'][ident]=draft;result={'draft_id':ident,'quote_robot_received':False}
        s['transfers'][token]={**result,'at':crawl.now(),'actor':user,'source_record':dict(r),'target':body.target};save(db,s)
    return s['transfers'][token]

@router.get('/export/{ident}')
def export(ident:str,fmt:Literal['json','csv','xlsx']='json',db:Session=Depends(get_db)):
    access.require(db,'CRAWLER_EXPORT');s=state(db);j=row(s,'jobs',ident)
    raw,mime=crawl.export([s['records'][i] for i in j['record_ids']],fmt)
    return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="ExpoCrawler-{ident}.{fmt}"','Cache-Control':'no-store'})

@router.get('/calendar')
def calendar(db:Session=Depends(get_db)):
    user=access.require(db,'CRAWLER_VIEW')
    return [{'id':e.id,'trade_show':e.event_name,'start_date':e.start_date,'end_date':e.end_date,'venue':e.venue,'city':e.city,'show_url':e.website} for e in db.query(Event).filter(Event.user_id==user).all()]
