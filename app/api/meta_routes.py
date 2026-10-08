"""Separate Meta OAuth consent and explicit Page/Professional selection; no posting in OAuth."""
import hashlib
import json
import secrets
import os
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.credentials import CredentialStore, remove_credentials
from app.core.security import utcnow
from app.models.models import SocialAccount, OAuthAttempt, ScheduledPost
from app.services import meta_channel as channel

router=APIRouter(prefix='/meta',tags=['meta'])

def digest(value):return hashlib.sha256(('meta:'+value).encode()).hexdigest()

def platform_name(platform):
    if platform not in channel.SCOPES:raise HTTPException(404,'Unsupported Meta channel')
    return platform

def origin(request):
    uri=urlsplit(os.getenv('META_REDIRECT_URI',''))
    if not request.headers.get('origin') or request.headers['origin']!=f'{uri.scheme}://{uri.netloc}':
        raise HTTPException(403,'Same-origin request required')

def config():
    try:return channel.oauth_config()
    except ValueError:raise HTTPException(409,'FACEBOOK_OWNER_ACTION_NEEDED: enter Meta App settings locally') from None

async def api(method,path,token=None,**kwargs):
    try:
        r=await channel.http.request(method,path,token,**kwargs)
        data=r.json()
        if r.status_code!=200 or not isinstance(data,dict) or 'error' in data:raise ValueError()
        return data
    except Exception:raise HTTPException(400,'Meta authorization/account operation failed; reconnect or check permissions') from None

async def token_expiry(data, cfg, received_at):
    # Log only fixed classifications, never provider strings or response bodies.
    token = data.get('access_token')
    ttl = data.get('expires_in')
    usable = isinstance(token, str) and bool(token)
    logging.getLogger(__name__).warning(
        'META_EXPIRY exchange_ok=true token_present=%s expires_in_present=%s expires_in_type=%s expires_in_zero=%s',
        usable, 'expires_in' in data, type(ttl).__name__, type(ttl) is int and ttl == 0)
    if not usable:
        raise HTTPException(400, 'Meta access token unavailable; reconnect')
    if type(ttl) is int and ttl > 0:
        try:
            expiry = received_at + timedelta(seconds=ttl)
        except OverflowError:
            raise HTTPException(400, 'Meta token expiry invalid; reconnect') from None
        source = 'expires_in'
    else:
        inspected = (await api('GET', 'debug_token', cfg['CLIENT_ID'] + '|' + cfg['CLIENT_SECRET'],
                               params={'input_token': token})).get('data')
        if not isinstance(inspected, dict):
            raise HTTPException(400, 'Meta token inspection invalid; reconnect')
        valid = inspected.get('is_valid') is True
        same_app = inspected.get('app_id') == cfg['CLIENT_ID']
        deadlines = []
        malformed = False
        for field in ('expires_at', 'data_access_expires_at'):
            value = inspected.get(field)
            if value is None:
                continue
            if type(value) is not int or value < 0:
                malformed = True
            elif value > 0:
                deadlines.append((value, 'debug_token.' + field))
        logging.getLogger(__name__).warning(
            'META_EXPIRY expires_at_present=%s expires_at_zero=%s data_access_expires_at_present=%s',
            'expires_at' in inspected, type(inspected.get('expires_at')) is int and inspected['expires_at'] == 0,
            'data_access_expires_at' in inspected)
        logging.getLogger(__name__).warning(
            'META_EXPIRY inspection_valid=%s app_matches=%s finite_deadlines=%s malformed=%s',
            valid, same_app, len(deadlines), malformed)
        if not valid or not same_app or malformed or not deadlines:
            raise HTTPException(400, 'Meta token expiry unavailable; reconnect')
        stamp, source = min(deadlines)
        try:
            expiry = datetime.fromtimestamp(stamp, timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError):
            raise HTTPException(400, 'Meta token expiry invalid; reconnect') from None
    if expiry <= utcnow() + timedelta(seconds=60):
        raise HTTPException(400, 'Meta token expired or near expiry; reconnect')
    logging.getLogger(__name__).warning('META_EXPIRY source=%s', source)
    return expiry, source

@router.post('/{platform}/oauth/start')
async def start(platform:str,request:Request,db:Session=Depends(get_db)):
    platform_name(platform);origin(request);cfg=config()
    state=secrets.token_urlsafe(48);nonce=secrets.token_urlsafe(32)
    request.session['meta_nonce']=nonce;request.session['meta_platform']=platform
    db.add(OAuthAttempt(user_id=db.info['owner_id'],state_hash=digest(state),browser_hash=digest(nonce+platform),expires_at=utcnow()+timedelta(minutes=10)))
    db.commit()
    return {'requested_permissions':sorted(channel.SCOPES[platform]),'authorization_url':
        f"https://www.facebook.com/{cfg['API_VERSION']}/dialog/oauth?"+urlencode({
            'client_id':cfg['CLIENT_ID'],'redirect_uri':cfg['REDIRECT_URI'],'response_type':'code',
            'scope':','.join(sorted(channel.SCOPES[platform])),'state':state})}

@router.get('/oauth/callback')
async def callback(request:Request,state:str='',code:str='',error:str='',db:Session=Depends(get_db)):
    nonce=request.session.pop('meta_nonce','');platform=request.session.pop('meta_platform','')
    attempt=db.query(OAuthAttempt).filter_by(user_id=db.info['owner_id'],state_hash=digest(state)).first()
    if not nonce or platform not in channel.SCOPES or not attempt or not secrets.compare_digest(attempt.browser_hash,digest(nonce+platform)):
        raise HTTPException(403,'Invalid OAuth state')
    changed=db.query(OAuthAttempt).filter(OAuthAttempt.id==attempt.id,OAuthAttempt.consumed==False,OAuthAttempt.expires_at>utcnow()).update({'consumed':True},synchronize_session=False)
    db.commit()
    if not changed:raise HTTPException(403,'Expired or consumed OAuth state')
    if error or not code:raise HTTPException(400,'Meta consent not completed')
    cfg=config()
    exchange_started=utcnow()
    data=await api('POST','oauth/access_token',data={'client_id':cfg['CLIENT_ID'],'client_secret':cfg['CLIENT_SECRET'],'redirect_uri':cfg['REDIRECT_URI'],'code':code})
    expiry,expiry_source=await token_expiry(data,cfg,exchange_started)
    token=data['access_token']
    permissions=await api('GET','me/permissions',token)
    granted={p['permission'] for p in permissions.get('data',[]) if p.get('status')=='granted'}
    if not channel.SCOPES[platform].issubset(granted):raise HTTPException(400,'Required Meta permissions not granted')
    fields='id,name,access_token,tasks'+(',instagram_business_account{id,username}' if platform=='instagram' else '')
    pages=[];after=None
    for _ in range(10):
        params={'fields':fields,'limit':100}
        if after:params['after']=after
        found=await api('GET','me/accounts',token,params=params)
        pages.extend(found.get('data',[]))
        paging=found.get('paging') or {}
        if not paging.get('next'):break
        after=(paging.get('cursors') or {}).get('after')
        if not after:raise HTTPException(400,'Incomplete Page discovery')
    else:raise HTTPException(400,'Page discovery exceeds safe bound')
    logging.getLogger(__name__).warning('META_DISCOVERY platform=%s page_count=%s',platform,len(pages))
    if platform=='instagram' and not pages:
        # Business-managed assets may not enumerate in /me/accounts. Reuse only an
        # existing owner-bound Page AND require fresh consent for that exact pair.
        inspected=(await api('GET','debug_token',cfg['CLIENT_ID']+'|'+cfg['CLIENT_SECRET'],params={'input_token':token})).get('data') or {}
        if inspected.get('is_valid') is not True or inspected.get('app_id')!=cfg['CLIENT_ID']:
            raise HTTPException(400,'Meta consent inspection invalid')
        targets={}
        for grant in inspected.get('granular_scopes',[]):
            targets.setdefault(grant.get('scope'),set()).update(grant.get('target_ids') or [])
        linked=db.query(SocialAccount).filter_by(user_id=db.info['owner_id'],platform='facebook',connection_status='connected').limit(10).all()
        for parent in linked:
            if not all(parent.account_id in targets.get(scope,set()) for scope in ('pages_show_list','pages_read_engagement')):continue
            try:
                channel.validate_account(parent,db)
                vault=CredentialStore()
                page_token=vault.get(db,parent.user_id,f'account:{parent.id}','access_token')
                binding=json.loads(vault.get(db,parent.user_id,f'account:{parent.id}','meta_binding'))
            except (ValueError,TypeError):continue
            detail=await api('GET',parent.account_id,page_token,params={'fields':'id,instagram_business_account{id,username}'})
            ig=detail.get('instagram_business_account') or {}
            if detail.get('id')!=parent.account_id:raise HTTPException(400,'Meta Page discovery identity mismatch')
            if not all(ig.get('id') in targets.get(scope,set()) for scope in ('instagram_basic','instagram_content_publish')):continue
            expiry=min(expiry,parent.token_expires_at)
            pages.append({'id':parent.account_id,'name':parent.account_name,'access_token':page_token,
                          'tasks':binding['tasks'],'instagram_business_account':ig})
        logging.getLogger(__name__).warning('META_DISCOVERY fresh_consent_bound_page_count=%s',len(pages))
    candidates=[]
    for page in pages:
        eligible=bool(channel.valid_id(page.get('id')) and page.get('name') and page.get('access_token') and {'CREATE_CONTENT','MANAGE'}.intersection(page.get('tasks',[])))
        logging.getLogger(__name__).warning('META_DISCOVERY platform=%s page_id_valid=%s page_token_present=%s content_task=%s',
            platform,channel.valid_id(page.get('id')),bool(page.get('access_token')),bool({'CREATE_CONTENT','MANAGE'}.intersection(page.get('tasks',[]))))
        if not eligible:continue
        ig=page.get('instagram_business_account') or {}
        if platform=='instagram' and (not channel.valid_id(ig.get('id')) or not ig.get('username')):
            # Resolve the documented Page edge with its own discovered Page token.
            detail=await api('GET',page['id'],page['access_token'],params={'fields':'id,instagram_business_account{id,username}'})
            if detail.get('id')!=page['id']:raise HTTPException(400,'Meta Page discovery identity mismatch')
            ig=detail.get('instagram_business_account') or {}
        logging.getLogger(__name__).warning('META_DISCOVERY platform=%s ig_id_valid=%s ig_username_present=%s',
            platform,channel.valid_id(ig.get('id')),bool(ig.get('username')))
        # This Page edge contains only Business/Creator IG users (Facebook Login API).
        # account_type is not a supported field on this API's IG User.
        if platform=='instagram' and (not channel.valid_id(ig.get('id')) or not isinstance(ig.get('username'),str) or not ig['username']):continue
        candidates.append({'page_id':page['id'],'external_id':page['id'] if platform=='facebook' else ig['id'],
            'display_name':page['name'] if platform=='facebook' else ig.get('username',page['name']),
            'tasks':page['tasks'],'token':page['access_token']})
    if not candidates:raise HTTPException(409,'FACEBOOK_OWNER_ACTION_NEEDED: authorize a Page with content task and linked Professional account where required')
    scope=f'meta-selection:{attempt.id}'
    CredentialStore().put(db,db.info['owner_id'],scope,'selection',json.dumps({'platform':platform,'pages':candidates,
        'requested':sorted(channel.SCOPES[platform]),'granted':sorted(granted),'expires':expiry.isoformat(),'expiry_source':expiry_source}))
    request.session['meta_selection']=attempt.id
    db.commit()
    return RedirectResponse('/meta',303,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

def selection(request,db):
    ident=request.session.get('meta_selection')
    row=db.query(OAuthAttempt).filter_by(id=ident,user_id=db.info['owner_id']).first()
    if not row or row.expires_at<=utcnow():raise HTTPException(409,'Selection expired; reconnect')
    try:data=json.loads(CredentialStore().get(db,db.info['owner_id'],f'meta-selection:{ident}','selection'))
    except ValueError:raise HTTPException(409,'Reconnect before selecting') from None
    return ident,data

@router.get('/selection')
async def candidates(request:Request,db:Session=Depends(get_db)):
    ident,data=selection(request,db)
    return {'platform':data['platform'],'requested_permissions':data['requested'],'granted_permissions':data['granted'],
            'candidates':[{k:v for k,v in p.items() if k!='token'} for p in data['pages']]}

class Binding(BaseModel):
    page_id:str
    external_id:str

@router.post('/selection')
async def bind(body:Binding,request:Request,db:Session=Depends(get_db)):
    origin(request);ident,data=selection(request,db)
    if datetime.fromisoformat(data['expires'])<=utcnow()+timedelta(seconds=60):
        raise HTTPException(409,'Meta token expired or near expiry; reconnect')
    matches=[p for p in data['pages'] if p['page_id']==body.page_id and p['external_id']==body.external_id]
    if len(matches)!=1:raise HTTPException(400,'Explicit unambiguous discovered account required')
    claimed=db.query(OAuthAttempt).filter(OAuthAttempt.id==ident,OAuthAttempt.expires_at>utcnow()).update({'expires_at':utcnow()},synchronize_session=False)
    if not claimed:raise HTTPException(409,'Selection already used; reconnect')
    p=matches[0];owner=db.info['owner_id'];platform=data['platform']
    account=db.query(SocialAccount).filter_by(user_id=owner,platform=platform,account_id=p['external_id']).first()
    if account and db.query(ScheduledPost).filter_by(social_account_id=account.id,status='processing').first():
        raise HTTPException(409,'Resolve in-flight job before reconnect')
    if account is None:
        account=SocialAccount(user_id=owner,platform=platform,account_id=p['external_id'],account_name=p['display_name'][:200]);db.add(account);db.flush()
    account.account_name=p['display_name'][:200];account.account_type='page' if platform=='facebook' else 'professional'
    account.is_mock_mode=False;account.is_active=True;account.connection_status='connected'
    account.scopes=' '.join(data['granted']);account.last_verified_at=utcnow()
    # Conservative expiry bounded by source user token; never assumes a never-expiring Page token.
    account.token_expires_at=datetime.fromisoformat(data['expires'])
    vault=CredentialStore();vault.put(db,owner,f'account:{account.id}','access_token',p['token'])
    vault.put(db,owner,f'account:{account.id}','meta_binding',json.dumps({'platform':platform,'page_id':p['page_id'],
        'external_id':p['external_id'],'tasks':p['tasks'],'requested_permissions':data['requested'],'granted_permissions':data['granted'],'expiry_source':data.get('expiry_source')}))
    remove_credentials(db,owner,f'meta-selection:{ident}');request.session.pop('meta_selection',None);db.commit()
    return {'id':account.id,'platform':platform,'external_id':account.account_id,'real_enabled':channel.real_enabled(platform)}

@router.get('/accounts')
async def accounts(db:Session=Depends(get_db)):
    rows=db.query(SocialAccount).filter(SocialAccount.platform.in_(channel.SCOPES)).all()
    def binding(a):
        try:
            d=json.loads(CredentialStore().get(db,a.user_id,f'account:{a.id}','meta_binding'))
            return {k:d.get(k) for k in ('page_id','requested_permissions','granted_permissions')}
        except ValueError:return {'page_id':None,'requested_permissions':[],'granted_permissions':[]}
    return {'switches':{p:channel.real_enabled(p) for p in channel.SCOPES},'configured':os.getenv('META_OAUTH_ENABLED')=='true',
        'accounts':[{'id':a.id,'platform':a.platform,'external_id':a.account_id,'display_name':a.account_name,
            'account_type':a.account_type,'owner_user_id':a.user_id,'connection_status':a.connection_status,
            **binding(a),'scopes':(a.scopes or '').split(),'token_expiry':a.token_expires_at,'last_verified_at':a.last_verified_at,
            'reauth_required':not a.token_expires_at or a.token_expires_at<=utcnow()+timedelta(seconds=60)} for a in rows]}

@router.post('/accounts/{account_id}/disconnect')
async def disconnect(account_id:int,request:Request,db:Session=Depends(get_db)):
    origin(request)
    a=db.query(SocialAccount).filter(SocialAccount.id==account_id,SocialAccount.platform.in_(channel.SCOPES)).first()
    if not a:raise HTTPException(404,'Account not found')
    if db.query(ScheduledPost).filter_by(social_account_id=a.id,status='processing').first():raise HTTPException(409,'Reconcile in-flight job first')
    remove_credentials(db,a.user_id,f'account:{a.id}');a.connection_status='disconnected';a.is_active=False
    db.query(ScheduledPost).filter(ScheduledPost.social_account_id==a.id,ScheduledPost.status.in_(['draft','scheduled','failed_retryable'])).update({'status':'cancelled'})
    db.commit()
    return {'success':True,'remote_revocation':'OWNER_ACTION_REQUIRED'}

class MetaJob(BaseModel):
    social_account_id:int
    campaign_id:int|None=None
    content_id:int|None=None
    content:str
    image_url:str|None=None
    idempotency_key:str
    execution_mode:str
    scheduled_at:str|None=None

@router.post('/{platform}/jobs')
async def job(platform:str,body:MetaJob,request:Request,db:Session=Depends(get_db)):
    platform_name(platform);origin(request)
    if body.execution_mode!='REAL' or not channel.real_enabled(platform):raise HTTPException(403,'Separate platform first-post approval required; switch disabled')
    from app.services.publishing import prepare_post,process_post
    image=None
    if platform=='instagram' and not body.image_url:raise HTTPException(400,'Instagram requires a JPEG image')
    if body.image_url:
        try:image=await channel.inspect_image(body.image_url,platform)
        except Exception:raise HTTPException(400,'Media accessibility or format validation failed') from None
    data=body.model_dump();data['platform']=platform;data['_meta_image']=image
    post=prepare_post(db,db.info['owner_id'],data,schedule=bool(body.scheduled_at));db.commit()
    if body.scheduled_at:
        from app.services.publishing import post_result
        return post_result(post)
    return await process_post(db,post)

@router.get('/jobs/{job_id}')
async def job_status(job_id:int,db:Session=Depends(get_db)):
    from app.services.publishing import post_result
    post=db.query(ScheduledPost).filter(ScheduledPost.id==job_id,ScheduledPost.platform.in_(channel.SCOPES)).first()
    if not post:raise HTTPException(404,'Job not found')
    def stored(kind):
        try:return json.loads(CredentialStore().get(db,post.user_id,f'job:{post.id}',kind))
        except ValueError:return None
    return {**post_result(post),'social_account_id':post.social_account_id,
            'media':stored('meta_payload'),'container':stored('meta_container')}
