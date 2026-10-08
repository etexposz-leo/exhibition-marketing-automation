"""Owner-only inspiration library, existing encrypted store; never schedules/publishes."""
import hashlib,threading,time,json,os,subprocess,uuid
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import utcnow
from app.models.models import CredentialMetadata
from app.api import unified_marketing as workspace,channel_workspace as channels
from app.services import content_inspiration as research
from app.services import original_copy
from app.services.ai_service import ai_service,AIService
from app.models.models import Campaign
from app.services.publishing import owned

router=APIRouter(prefix='/marketing/inspiration',tags=['content inspiration'])
LOCK=threading.RLock()
LAST_REQUEST={}
PREFIX='content-inspiration:'

class Capture(BaseModel):
    url:str=Field(min_length=8,max_length=2000)

class Import(Capture):
    title:str=Field(default='',max_length=300)
    excerpt:str=Field(min_length=40,max_length=400)
    likes:int|None=Field(default=None,ge=0,le=10**12)
    notes:str=Field(default='',max_length=2000)

class Update(BaseModel):
    revision:str
    status:str
    notes:str=Field(default='',max_length=2000)

def record(db,ident):
    value=workspace.load_record(db,PREFIX+ident)
    if not value:raise HTTPException(404,'文案记录不存在。')
    return value

def present(value):
    return {**value,'revision':workspace.fingerprint(value)}

def persist(db,doc):
    ident=hashlib.sha256(doc['source_url'].encode()).hexdigest()[:32]
    with LOCK:
        previous=workspace.load_record(db,PREFIX+ident)
        if previous:return {'item':present(previous),'duplicate':True}
        count=db.query(CredentialMetadata).filter(CredentialMetadata.user_id==channels.owner(db),CredentialMetadata.scope.like(PREFIX+'%')).count()
        if count>=200:raise HTTPException(409,'本地第一版最多保存 200 条，请先整理文案库。')
        value=research.annotate({**doc,'id':ident,'captured_at':utcnow().isoformat(),'status':'PENDING_REVIEW','notes':doc.get('notes','')})
        workspace.save_record(db,PREFIX+ident,value)
        return {'item':present(value),'duplicate':False}

@router.get('')
def listing(db:Session=Depends(get_db)):
    workspace.backlink_owner(db)
    rows=db.query(CredentialMetadata).filter(CredentialMetadata.user_id==channels.owner(db),CredentialMetadata.scope.like(PREFIX+'%')).order_by(CredentialMetadata.id.desc()).all()
    return {'items':[present(record(db,r.scope[len(PREFIX):])) for r in rows],
        'platforms':[{'id':p,'mode':'PUBLIC_SEARCH_INDEX','automatic_keyword_search':True,
                      'public_engagement_adapter_available':p=='youtube'} for p in research.PLATFORMS],
        'topics':['展会搭建','展台设计','参展营销'],'engine':'DDGS + yt-dlp + Trafilatura',
        'ai_available':configured_ai(db).is_available(),
        'brand_facts':workspace.load_record(db,'original-brand-facts',default={}),
        'last_discovery':workspace.load_record(db,'last-discovery',default={}),
        'real_publish_enabled':False}

class Discovery(BaseModel):
    platform:str
    keyword:str=Field(default='trade show booth design',min_length=2,max_length=120)
    limit:int=Field(default=3,ge=1,le=5)
    min_views:int=Field(default=10000,ge=1,le=10**12)
    min_likes:int=Field(default=100,ge=1,le=10**12)
    max_age_days:int=Field(default=730,ge=1,le=3650)

@router.post('/discover')
def discover(body:Discovery,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    if body.platform not in research.PLATFORMS:raise HTTPException(400,'未知平台。')
    domains=research.PLATFORMS[body.platform]
    query=body.keyword+(' site:'+domains[0] if domains else '')
    with LOCK:
        who=channels.owner(db);now=time.monotonic()
        if now-LAST_REQUEST.get(('search',who),-100)<5:raise HTTPException(429,'搜索至少间隔 5 秒。')
        LAST_REQUEST[('search',who)]=now
    try:
        result=subprocess.run([str(research.ROOT/'.venv-content/Scripts/python.exe'),'-X','utf8','-B',str(research.ROOT/'scripts/discover_posts.py')],
            input=json.dumps({'query':query,'limit':body.limit}),capture_output=True,text=True,encoding='utf-8',timeout=55,
            env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP'}})
        output=json.loads(result.stdout) if result.returncode==0 else {'status':'BLOCKED','results':[]}
    except (OSError,ValueError,subprocess.TimeoutExpired):output={'status':'BLOCKED','results':[]}
    summary={'platform':body.platform,'query':query,'at':utcnow().isoformat(),'status':output.get('status','BLOCKED'),'saved':0,'duplicates':0,'filtered':0,'popular_candidates':0}
    for item in output.get('results',[])[:body.limit]:
        try:url=research.normalize_url(item.get('source_url',''))
        except research.CollectionError:summary['filtered']+=1;continue
        if domains and research.platform_for(url)!=body.platform:summary['filtered']+=1;continue
        if not item.get('title') or not item.get('excerpt'):summary['filtered']+=1;continue
        item.update(source_url=url,resolved_url=url,platform=research.platform_for(url),discovery_query=query)
        item['heat_evidence']=original_copy.heat(item,body.min_views,body.min_likes,body.max_age_days)
        saved=persist(db,item)
        if saved['duplicate']:summary['duplicates']+=1
        else:summary['saved']+=1
        if saved['item'].get('heat_evidence',{}).get('status')=='POPULAR_CANDIDATE':summary['popular_candidates']+=1
    if summary['status']=='COMPLETE' and not summary['saved'] and not summary['duplicates']:summary['status']='NO_MATCHING_RESULTS'
    workspace.save_record(db,'last-discovery',summary)
    return summary

def configured_ai(db):
    settings=workspace.load_record(db,'original-ai-settings',default={})
    if not settings:return ai_service
    service=AIService()
    service.openai_api_key=settings['key'] if settings['provider']=='openai' else ''
    service.deepseek_api_key=settings['key'] if settings['provider']=='deepseek' else ''
    return service

@router.post('/ai-settings')
async def ai_settings(request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    raw=await request.body()
    if len(raw)>4096:raise HTTPException(400,'配置过长。')
    try:body=json.loads(raw)
    except ValueError:raise HTTPException(400,'配置格式无效。') from None
    if not isinstance(body,dict) or body.get('provider') not in {'openai','deepseek'} or not isinstance(body.get('key'),str) or not 16<=len(body['key'].strip())<=2048:
        raise HTTPException(400,'请选择服务并填写有效 API Key。')
    workspace.save_record(db,'original-ai-settings',{'provider':body['provider'],'key':body['key'].strip()})
    return {'saved':True,'connection_tested':False}

class BrandFacts(BaseModel):
    facts:str=Field(min_length=10,max_length=4000)
    confirmed:bool=False

@router.post('/brand-facts')
def brand_facts(body:BrandFacts,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    if not body.confirmed:raise HTTPException(400,'请先确认这些是 ET EXPO 的真实信息。')
    workspace.save_record(db,'original-brand-facts',{'facts':body.facts,'confirmed':True,'confirmed_at':utcnow().isoformat()})
    return {'saved':True}

class Rewrite(BaseModel):
    source_id:str
    campaign_id:int
    platform:str
    language:str='zh'
    mode:str='local'
    angle:str=Field(default='',max_length=500)

@router.post('/rewrite')
async def rewrite(body:Rewrite,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db);owned(db,Campaign,body.campaign_id,channels.owner(db))
    if body.platform not in channels.CHANNELS or body.language not in {'zh','en'} or body.mode not in {'local','ai'}:raise HTTPException(400,'创作参数无效。')
    source=record(db,body.source_id)
    facts=workspace.load_record(db,'original-brand-facts',default={})
    if not facts.get('confirmed'):raise HTTPException(409,'请先填写并确认 ET EXPO 品牌事实，不能使用别人的案例或成绩。')
    service=configured_ai(db)
    if body.mode=='ai':
        if not service.is_available():raise HTTPException(503,'AI 尚未配置；未自动切换成模板。')
        try:
            import asyncio
            caption=await asyncio.wait_for(service.generate_content(original_copy.prompt(source,facts['facts'],body.language,body.angle),provider=service.get_provider_name(),max_tokens=1200),timeout=40)
        except Exception:raise HTTPException(502,'AI 生成失败；没有保存或发布，服务错误详情已隐藏。') from None
        finally:
            if service is not ai_service:
                for client in (service.openai_client,service.deepseek_client):
                    if client is not None:await client.close()
    else:caption=original_copy.local_original(source,facts['facts'],body.language)
    if not isinstance(caption,str) or not caption.strip() or len(caption)>10000:raise HTTPException(502,'生成结果为空或超出长度限制。')
    proposal={'id':uuid.uuid4().hex,'source_id':source['id'],'source_url':source['source_url'],'source_excerpt':source['excerpt'],
        'caption':caption,'mode':body.mode,'campaign_id':body.campaign_id,'platform':body.platform,'brand_facts':facts['facts'],
        'created_at':utcnow().isoformat(),'status':'PENDING_REVIEW','originality':original_copy.overlap(source['excerpt'],caption)}
    from app.services import sales_copy
    proposal['sales_brief']=sales_copy.analyze(sales_copy.Brief(target_audience='Exhibitor teams',topic=body.angle,
        sources=[dict(reference='Owner-confirmed brand facts',text=facts['facts'],confirmed=True)]))
    proposal['sales_gate']=sales_copy.evaluate(caption,body.platform,proposal['sales_brief'])
    workspace.save_record(db,'original-proposal:'+proposal['id'],proposal)
    return proposal

class ProposalReview(BaseModel):
    proposal_id:str
    caption:str=Field(min_length=20,max_length=10000)
    facts_reviewed:bool=False

@router.post('/rewrite/save-draft')
def save_rewrite(body:ProposalReview,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    with LOCK:
        p=workspace.load_record(db,'original-proposal:'+body.proposal_id)
        if not p:raise HTTPException(404,'创作记录不存在。')
        if p.get('draft_id'):raise HTTPException(409,'此创作记录已进入草稿队列，请在队列编辑。')
        check=original_copy.overlap(p['source_excerpt'],body.caption)
        if check['status']=='HIGH_OVERLAP':raise HTTPException(409,'与参考摘要重合过高，请重写后再保存。')
        if not body.facts_reviewed:raise HTTPException(400,'请确认事实、案例归属和原创表达后再保存。')
        db.info['original_draft_transaction']=True
        db.info['sales_brief_context']=p.get('sales_brief')
        try:
            result=workspace.social_draft(workspace.SocialDraft(campaign_id=p['campaign_id'],platform=p['platform'],caption=body.caption),request,db)
            workspace.save_record(db,'originality:'+str(result['id']),{'source_excerpt':p['source_excerpt'],'source_url':p['source_url'],'proposal_id':p['id'],'check':check,'facts_reviewed':True})
            p.update(draft_id=result['id'],status='DRAFT_CREATED');workspace.save_record(db,'original-proposal:'+p['id'],p)
            db.commit()
        except Exception:
            db.rollback();raise
        finally:
            db.info.pop('original_draft_transaction',None)
            db.info.pop('sales_brief_context',None)
        return {'draft_id':result['id'],'status':'DRAFT','published':False,'originality':check}

@router.post('/capture')
def capture(body:Capture,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    try:url=research.normalize_url(body.url)
    except research.CollectionError as exc:raise HTTPException(400,str(exc)) from None
    with LOCK:
        who=channels.owner(db);now=time.monotonic()
        if now-LAST_REQUEST.get(who,-100)<5:raise HTTPException(429,'请至少间隔 5 秒再采集；不进行批量高频请求。')
        LAST_REQUEST[who]=now
    try:return persist(db,research.collect(url))
    except research.CollectionError as exc:raise HTTPException(422,str(exc)) from None

@router.post('/import')
def import_excerpt(body:Import,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    try:url=research.normalize_url(body.url)
    except research.CollectionError as exc:raise HTTPException(400,str(exc)) from None
    return persist(db,{'source_url':url,'resolved_url':url,'platform':research.platform_for(url),
        'title':body.title,'excerpt':body.excerpt,'author':'','published_at':None,'notes':body.notes,
        'capture_method':'OWNER_IMPORT','metrics':{'likes':body.likes} if body.likes is not None else {},
        'metrics_source':'OWNER_PROVIDED_UNVERIFIED' if body.likes is not None else 'UNAVAILABLE'})

@router.post('/{ident}/review')
def review(ident:str,body:Update,request:Request,db:Session=Depends(get_db)):
    channels.origin(request);workspace.backlink_owner(db)
    if body.status not in {'SAVED','REJECTED','PENDING_REVIEW'}:raise HTTPException(400,'未知审核状态。')
    with LOCK:
        value=record(db,ident)
        if body.revision!=workspace.fingerprint(value):raise HTTPException(409,'记录已变化，请刷新后审核。')
        value.update(status=body.status,notes=body.notes,reviewed_at=utcnow().isoformat())
        workspace.save_record(db,PREFIX+ident,value)
        return present(value)
