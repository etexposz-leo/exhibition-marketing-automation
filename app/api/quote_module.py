"""Embedded Owner-only Quote Robot intake, preserving original pricing guards."""
import hashlib,json,os,subprocess,threading,uuid,re
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import FileResponse,HTMLResponse
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import module_access as access
from app.api import unified_marketing as records,expo_module
from app.api.channel_workspace import origin

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(r'F:\报价机器人ai')
BRIDGE=ROOT/'scripts/quote_workspace.py'
PYTHON=SOURCE/'.venv/Scripts/python.exe'
TEMPLATE=SOURCE/'templates/ET US EXPO LLC Estimation_Master_Template.xlsm'
HASH='4959eda15d2b0d02461fc2a7e550d20e'
SCOPE='quote-workspace-v1';LOCK=threading.RLock()
router=APIRouter(prefix='/marketing/modules/quote',tags=['Embedded Quote Robot'])

def require(db):
    user=access.require(db,'QUOTE_ROBOT_ACCESS')
    if user!=access.primary_owner():raise HTTPException(403,'Quote Robot workspace is currently Owner-only')
    return user
def home(user):return ROOT/'data/modules/quote'/str(user)
def state(db):return records.load_record(db,SCOPE,default={})
def call(user,action,ident,info,provenance=None):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','LOCALAPPDATA','APPDATA','USERPROFILE'}}
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    try:
        r=subprocess.run([str(PYTHON),'-X','utf8','-B',str(BRIDGE),str(home(user))],input=json.dumps({'action':action,'id':ident,'info':info,'provenance':provenance or {}}),text=True,encoding='utf-8',capture_output=True,timeout=90,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=json.loads(r.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired):raise HTTPException(503,'Quote Robot intake runtime unavailable')
    if r.returncode or not result.get('ok'):raise HTTPException(409,'Quote Robot intake failed; inspect local baseline before retrying')
    return result['result']
def template_ready():return TEMPLATE.is_file() and hashlib.md5(TEMPLATE.read_bytes()).hexdigest()==HASH

class Info(BaseModel):
    company:str=Field(min_length=1,max_length=180)
    show:str=Field(min_length=1,max_length=180)
    booth:str=Field(default='',max_length=100)
    booth_size:str=Field(default='',max_length=100)
    year:str=Field(default='',max_length=4)
    customer_mode:str=Field(default='',max_length=40)
    contact:str=Field(default='',max_length=180)
    email:str=Field(default='',max_length=180)
    notes:str=Field(default='',max_length=5000)
def mapped(v):
    return {'Client':v.company,'Exhibitor Name':v.company,'Show Name':v.show,'Booth No':v.booth,'Booth Size':v.booth_size,'Year':v.year,'Customer Quote Mode':v.customer_mode,'Contact Person':v.contact,'Email':v.email,'Description':v.notes,'Created By':'Unified Owner','Quotation Template':str(TEMPLATE)}
def missing(v):
    return [label for field,label in [('booth_size','展位尺寸'),('customer_mode','客户报价模式')] if not v.get(field)]+['报价明细与明确价格审批','真实报价工作簿重开验证']

@router.get('')
def listing(db:Session=Depends(get_db)):
    require(db)
    approved=[{'id':r['id'],'company':r['company_name'],'show':r['trade_show'],'booth':r['booth_number'],'source_url':r['source_url']} for r in expo_module.state(db)['records'].values() if r['status']=='APPROVED']
    return {'projects':list(state(db).values()),'approved_sources':approved,'template_verified':template_ready(),'desktop_launch_required':False,'automatic_pricing':False,'customer_send_enabled':False,'quote_generation_status':'BLOCKED_PENDING_PRICING_AND_WORKBOOK_VALIDATION'}

@router.post('/projects')
def create(v:Info,request:Request,db:Session=Depends(get_db)):
    origin(request);user=require(db)
    if v.customer_mode not in {'','Exhibition Agent','Regular Client'}:raise HTTPException(400,'Choose an explicit customer mode')
    with LOCK:
        ident=uuid.uuid4().hex
        result=call(user,'create',ident,mapped(v),{'source':'OWNER_ENTERED','owner_id':user})
        s=state(db);s[ident]={'id':ident,'fields':v.model_dump(),'status':'PROJECT_INFO_DRAFT','provenance':{'source':'OWNER_ENTERED'},'missing':missing(v.model_dump()),**result};records.save_record(db,SCOPE,s);access.audit(db,'QUOTE_INTAKE_CREATED',ident)
    return s[ident]

@router.post('/from-crawler/{ident}')
def from_crawler(ident:str,request:Request,db:Session=Depends(get_db)):
    origin(request);user=require(db)
    with LOCK:
        s=state(db)
        for p in s.values():
            if p['provenance'].get('record_id')==ident:return {**p,'duplicate':True}
        crawled=expo_module.state(db);r=crawled['records'].get(ident)
        if not r or r['status']!='APPROVED':raise HTTPException(409,'Approved source record required')
        if ident+':leads' not in crawled['transfers']:raise HTTPException(409,'Reviewed lead handoff required')
        v=Info(company=r['company_name'],show=r['trade_show'],booth=r['booth_number'],year=r.get('start_date','')[:4],notes='Source: '+r['source_url'])
        key=uuid.uuid4().hex;proof={'record_id':ident,'source_url':r['source_url'],'source_excerpt':r.get('source_excerpt',''),'source_hash':r.get('source_hash',r.get('content_hash','')),'company':r['company_name'],'show':r['trade_show'],'booth':r['booth_number'],'original_record':r}
        result=call(user,'create',key,mapped(v),proof)
        s[key]={'id':key,'fields':v.model_dump(),'status':'PROJECT_INFO_DRAFT','provenance':proof,'missing':missing(v.model_dump()),**result};records.save_record(db,SCOPE,s);access.audit(db,'QUOTE_CRAWLER_RECEIVED',key)
        return s[key]

@router.post('/projects/{ident}')
def edit(ident:str,v:Info,request:Request,db:Session=Depends(get_db)):
    origin(request);user=require(db)
    if v.customer_mode not in {'','Exhibition Agent','Regular Client'}:raise HTTPException(400,'Choose an explicit customer mode')
    with LOCK:
        s=state(db)
        if ident not in s:raise HTTPException(404,'Project not found')
        call(user,'edit',ident,mapped(v));s[ident]['fields']=v.model_dump();s[ident]['missing']=missing(v.model_dump());records.save_record(db,SCOPE,s);access.audit(db,'QUOTE_INFO_SAVED',ident)
    return s[ident]

@router.get('/projects/{ident}/files/{name}')
def download(ident:str,name:str,db:Session=Depends(get_db)):
    user=require(db)
    if ident not in state(db) or name not in {'project_info.xlsx','project_info_cover.xlsx','source-provenance.json'}:raise HTTPException(404,'File not found')
    p=home(user)/'projects'/('ETM_'+ident)/name
    if not p.is_file():raise HTTPException(404,'File not found')
    return FileResponse(p,filename=name,headers={'Cache-Control':'private, no-store'})

@router.get('/projects/{ident}/preview')
def preview(ident:str,db:Session=Depends(get_db)):
    user=require(db)
    if ident not in state(db):raise HTTPException(404,'Project not found')
    p=home(user)/'projects'/('ETM_'+ident)/'reports/project_info_cover.html'
    if not p.is_file():raise HTTPException(404,'Preview unavailable')
    html=p.read_text(encoding='utf-8').replace('body { font-family','body { background:#fff; font-family')
    html=re.sub(r'<img src="[^"]*" alt="ET EXPO logo">','<strong>ET EXPO</strong>',html)
    return HTMLResponse(html,headers={'Cache-Control':'private, no-store','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox; frame-ancestors 'self'"})
