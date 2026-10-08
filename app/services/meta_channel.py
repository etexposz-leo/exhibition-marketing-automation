"""Meta Page/Professional channels. No provider retries hidden inside transport."""
import os
import re
import json
from datetime import timedelta
from urllib.parse import urlsplit
import httpx
from app.core.credentials import CredentialStore
from app.core.security import utcnow
from app.services.platform_adapter import BasePlatformAdapter, PlatformConfig, PlatformType, PublishResult

SCOPES = {
    'facebook': {'pages_show_list', 'pages_read_engagement', 'pages_manage_posts'},
    'instagram': {'pages_show_list', 'pages_read_engagement', 'instagram_basic', 'instagram_content_publish'},
}

def version():
    value = os.getenv('META_API_VERSION', '')
    if not re.fullmatch(r'v\d+\.0', value):
        raise ValueError('Explicit supported Meta API version required')
    return value

def oauth_config():
    cfg = {k: os.getenv('META_' + k, '') for k in ('CLIENT_ID', 'CLIENT_SECRET', 'REDIRECT_URI')}
    uri = urlsplit(cfg['REDIRECT_URI'])
    if (os.getenv('META_OAUTH_ENABLED') != 'true' or not all(cfg.values())
            or uri.scheme != 'https' or not uri.hostname or uri.username or uri.query or uri.fragment
            or uri.path != '/api/meta/oauth/callback'):
        raise ValueError('FACEBOOK_OWNER_ACTION_NEEDED: configure Meta App locally')
    cfg['API_VERSION'] = version()
    return cfg

def real_enabled(platform):
    return platform in SCOPES and os.getenv(platform.upper() + '_REAL_PUBLISH_ENABLED') == 'true'

class MetaHTTP:
    async def request(self, method, path, token=None, **kwargs):
        if path != 'debug_token' and not re.fullmatch(r'(?:me|oauth|\d+(?:_\d+)?)(?:/[a-z_]+)?', path):
            raise ValueError('Invalid Meta endpoint')
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        async with httpx.AsyncClient(timeout=25, follow_redirects=False, trust_env=False) as client:
            return await client.request(method, 'https://graph.facebook.com/' + version() + '/' + path,
                                        headers=headers, **kwargs)
http = MetaHTTP()

def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[1-9]\d{3,39}', value))

def validate_account(account, db=None):
    if (not account or account.platform not in SCOPES or not account.is_active or account.is_mock_mode
            or account.connection_status != 'connected' or not account.last_verified_at
            or not valid_id(account.account_id)
            or account.account_type != ('page' if account.platform == 'facebook' else 'professional')
            or not SCOPES[account.platform].issubset(set((account.scopes or '').split()))
            or not account.token_expires_at or account.token_expires_at <= utcnow() + timedelta(seconds=60)):
        raise ValueError('Verified Meta account, permissions and valid token required')
    if db is not None:
        binding = json.loads(CredentialStore().get(db, account.user_id, f'account:{account.id}', 'meta_binding'))
        if (not valid_id(binding.get('page_id')) or not {'CREATE_CONTENT', 'MANAGE'}.intersection(binding.get('tasks', []))
                or binding.get('external_id') != account.account_id or binding.get('platform') != account.platform):
            raise ValueError('Verified Page binding required')


def media_url(value):
    uri = urlsplit(value or '')
    # Exact origin allowlist is supplied by owner/deployment, never by request data.
    hosts = set(os.getenv('META_MEDIA_HOSTS', '').lower().split(',')) - {''}
    if (uri.scheme != 'https' or uri.hostname not in hosts or uri.username or uri.password
            or uri.port not in (None, 443) or uri.fragment or uri.query):
        raise ValueError('Public HTTPS media URL on approved host required; signed/query URLs are not accepted')
    return value

async def inspect_image(url, platform):
    """Bounded GET only. Never uploads media or follows redirects."""
    import io
    import socket
    import ipaddress
    from PIL import Image
    media_url(url)
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Media host must resolve publicly')
    blob = bytearray()
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        async with client.stream('GET', url) as response:
            if response.status_code != 200 or response.headers.get('content-type','').split(';')[0] != 'image/jpeg':
                raise ValueError('Accessible JPEG response required')
            async for chunk in response.aiter_bytes():
                blob.extend(chunk)
                if len(blob) > 8 * 1024 * 1024:
                    raise ValueError('Image exceeds 8 MB')
    try:
        with Image.open(io.BytesIO(blob)) as im:
            width, height = im.size
            if im.format != 'JPEG' or width * height > 40_000_000:
                raise ValueError()
            im.load()
        if platform == 'instagram' and not (320 <= width <= 1440 and 0.8 <= width / height <= 1.91):
            raise ValueError()
    except Exception:
        raise ValueError('JPEG dimensions/aspect ratio invalid') from None
    import hashlib
    return {'url':url, 'format':'JPEG', 'width':width, 'height':height, 'bytes':len(blob),
            'sha256':hashlib.sha256(blob).hexdigest()}


def failure(platform, code, **metadata):
    return PublishResult(False, platform, error=code, execution_mode='REAL', metadata=metadata)

async def call(platform, method, path, token, account, **kwargs):
    try:
        response = await http.request(method, path, token, **kwargs)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        return None, failure(platform, 'connection_not_established', retryable=True)
    except Exception:
        return None, failure(platform, 'delivery_uncertain', uncertain=True)
    try:
        data = response.json()
        if not isinstance(data, dict): raise ValueError()
    except Exception:
        return None, failure(platform, 'invalid_provider_response', uncertain=True)
    if 200 <= response.status_code < 300 and 'error' not in data:
        return data, None
    error = data.get('error') or {}
    code = error.get('code') if isinstance(error, dict) else None
    if code == 190 or response.status_code == 401:
        account.connection_status = 'reauth_required'
        return None, failure(platform, 'reauth_required')
    if response.status_code == 429 or code in {4, 17, 32, 613, 80001}:
        delay = response.headers.get('retry-after','')
        return None, failure(platform, 'rate_limited', retryable=True,
                             retry_after=min(max(int(delay),60),86400) if delay.isdigit() else 300)
    if response.status_code >= 500 or response.status_code in {408,409}:
        return None, failure(platform, 'provider_outcome_uncertain', uncertain=True)
    return None, failure(platform, 'provider_rejected_' + str(response.status_code))

class MetaAdapter(BasePlatformAdapter):
    def __init__(self, platform):
        self.platform = platform
        self.config = PlatformConfig(PlatformType(platform), platform.title(), platform, '#1877F2',
                                     2200 if platform == 'instagram' else 63206, True)
    def is_configured(self):
        return real_enabled(self.platform) and bool(re.fullmatch(r'v\d+\.0', os.getenv('META_API_VERSION','')))
    def validate_content(self, content):
        valid, error = super().validate_content(content)
        if self.platform == 'instagram' and (len(re.findall(r'(?<!\w)#\w+',content))>30 or len(re.findall(r'(?<!\w)@\w+',content))>20):
            return False, 'Instagram caption exceeds hashtag/mention limit'
        return valid,error
    async def publish(self, content, *, db=None, account=None, post=None, **kwargs):
        p = self.platform
        if not real_enabled(p): raise ValueError('Separate platform owner approval required')
        validate_account(account, db)
        if db is None or db.info.get('owner_id') != account.user_id or post is None or post.platform != p or account.platform != p:
            raise ValueError('Owned persistent job required')
        if not self.validate_content(content)[0]: raise ValueError('Invalid content')
        vault = CredentialStore()
        scope = f'job:{post.id}'
        payload = json.loads(vault.get(db, post.user_id, scope, 'meta_payload'))
        image = payload.get('image')
        if p == 'instagram' and not image: raise ValueError('Instagram image required')
        if image:
            observed = await inspect_image(image['url'], p)
            if observed != image: raise ValueError('Reviewed media changed; new approval required')
        token = vault.get(db, account.user_id, f'account:{account.id}', 'access_token')
        if p == 'facebook':
            path = account.account_id + ('/photos' if image else '/feed')
            body = {'message': content}
            if image: body.update(url=image['url'], published='true')
            result, err = await call(p,'POST',path,token,account,data=body)
            if err:return err
            ident = result.get('post_id') if image else result.get('id')
            if not isinstance(ident,str) or not re.fullmatch(re.escape(account.account_id)+r'_\d+',ident):
                return failure(p,'confirmation_missing_identifier',uncertain=True)
        else:
            # Persist container before polling or publishing. A crash remains quarantined by scheduler.
            try: checkpoint=json.loads(vault.get(db,post.user_id,scope,'meta_container'))
            except ValueError: checkpoint={}
            container=checkpoint.get('id')
            if not container:
                result,err=await call(p,'POST',account.account_id+'/media',token,account,
                    data={'image_url':image['url'],'caption':content})
                if err:return err
                container=result.get('id')
                if not valid_id(container):return failure(p,'container_identifier_missing',uncertain=True)
                vault.put(db,post.user_id,scope,'meta_container',json.dumps({'id':container,'status':'CREATED'}));db.commit()
            result,err=await call(p,'GET',container,token,account,params={'fields':'status_code'})
            if err:return err
            state=result.get('status_code')
            vault.put(db,post.user_id,scope,'meta_container',json.dumps({'id':container,'status':state}));db.commit()
            if state=='IN_PROGRESS':return failure(p,'media_processing',retryable=True,retry_after=60)
            if state in {'ERROR','EXPIRED'}:return failure(p,'media_'+state.lower())
            if state!='FINISHED':return failure(p,'media_result_uncertain',uncertain=True)
            result,err=await call(p,'POST',account.account_id+'/media_publish',token,account,data={'creation_id':container})
            if err:return err
            ident=result.get('id')
            if not valid_id(ident):return failure(p,'confirmation_missing_identifier',uncertain=True)
        # Publication is confirmed even if optional permalink read fails. Never repeat the write.
        url=None
        try:
            response=await http.request('GET',ident,token,params={'fields':'permalink' if p=='instagram' else 'permalink_url'})
            candidate=response.json().get('permalink' if p=='instagram' else 'permalink_url')
            uri=urlsplit(candidate or '')
            if response.status_code==200 and uri.scheme=='https' and uri.hostname in {'www.facebook.com','facebook.com','www.instagram.com','instagram.com'} and not uri.username:
                url=candidate
        except Exception:pass
        return PublishResult(True,p,post_id=ident,url=url,published_at=utcnow().isoformat(),
                             execution_mode='REAL',metadata={'confirmed':True})
