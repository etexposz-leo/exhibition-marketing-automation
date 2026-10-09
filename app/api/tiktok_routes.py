"""Read-only TikTok channel authorization; publishing is deliberately unavailable."""
import hashlib
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.credentials import CredentialStore, remove_credentials
from app.core.security import utcnow
from app.models.models import OAuthAttempt, SocialAccount

router = APIRouter(prefix='/tiktok', tags=['tiktok'])
SCOPE = 'user.info.basic'
CALLBACK = '/api/tiktok/oauth/callback'


def config():
    cfg = {key: os.getenv('TIKTOK_' + key, '').strip() for key in ('CLIENT_KEY', 'CLIENT_SECRET', 'REDIRECT_URI')}
    missing = ['TIKTOK_' + key for key, value in cfg.items() if not value]
    if os.getenv('TIKTOK_OAUTH_ENABLED') != 'true':
        missing.append('TIKTOK_OAUTH_ENABLED')
    if missing:
        raise HTTPException(503, {'message': 'TikTok OAuth is not configured', 'fields': missing})
    try:
        uri = urlsplit(cfg['REDIRECT_URI'])
        valid = uri.scheme == 'https' and uri.hostname and not uri.username and not uri.password and not uri.query and not uri.fragment and uri.path == CALLBACK
        uri.port
    except ValueError:
        valid = False
    if valid and os.getenv('MARKETING_CLOUD_MODE') == 'true':
        from app.core.cloud_runtime import base_url
        valid = valid and uri.hostname not in ('localhost', '127.0.0.1', '::1') and cfg['REDIRECT_URI'] == base_url() + CALLBACK
    if not valid:
        raise HTTPException(503, {'message': 'TikTok HTTPS callback must match the application origin', 'fields': ['TIKTOK_REDIRECT_URI', 'APP_BASE_URL']})
    return cfg


def digest(value):
    return hashlib.sha256(('tiktok:' + value).encode()).hexdigest()


async def provider(method, url, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = await client.request(method, url, **kwargs)
        if response.status_code != 200:
            raise ValueError()
        data = response.json()
        if not isinstance(data, dict) or (data.get('error') and (not isinstance(data['error'], dict) or data['error'].get('code') != 'ok')):
            raise ValueError()
        return data
    except Exception:
        raise HTTPException(400, 'TikTok authorization request failed; reconnect or check TikTok app permissions') from None


@router.post('/oauth/start')
async def start(request: Request, db: Session = Depends(get_db)):
    cfg = config()
    uri = urlsplit(cfg['REDIRECT_URI'])
    if request.headers.get('origin') != f'{uri.scheme}://{uri.netloc}':
        raise HTTPException(403, 'Same-origin request required')
    state, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    request.session['tiktok_nonce'] = nonce
    db.add(OAuthAttempt(user_id=db.info['owner_id'], state_hash=digest(state), browser_hash=digest(nonce), expires_at=utcnow()+timedelta(minutes=10)))
    db.commit()
    return {'authorization_url': 'https://www.tiktok.com/v2/auth/authorize/?' + urlencode({
        'client_key': cfg['CLIENT_KEY'], 'redirect_uri': cfg['REDIRECT_URI'], 'response_type': 'code',
        'scope': SCOPE, 'state': state, 'disable_auto_auth': '1'})}


@router.get('/oauth/callback')
async def callback(request: Request, state: str = '', code: str = '', error: str = '', db: Session = Depends(get_db)):
    nonce = request.session.pop('tiktok_nonce', '')
    attempt = db.query(OAuthAttempt).filter_by(user_id=db.info['owner_id'], state_hash=digest(state)).first()
    if not nonce or not attempt or not secrets.compare_digest(attempt.browser_hash, digest(nonce)):
        raise HTTPException(403, 'Invalid TikTok OAuth state')
    consumed = db.query(OAuthAttempt).filter(OAuthAttempt.id == attempt.id, OAuthAttempt.consumed == False,
        OAuthAttempt.expires_at > utcnow()).update({'consumed': True}, synchronize_session=False)
    db.commit()
    if not consumed:
        raise HTTPException(403, 'TikTok OAuth state expired or already consumed')
    if error or not code:
        raise HTTPException(400, 'TikTok authorization was not completed')
    cfg = config()
    data = await provider('POST', 'https://open.tiktokapis.com/v2/oauth/token/', data={
        'grant_type': 'authorization_code', 'code': code, 'client_key': cfg['CLIENT_KEY'],
        'client_secret': cfg['CLIENT_SECRET'], 'redirect_uri': cfg['REDIRECT_URI']})
    token = data.get('access_token')
    try:
        ttl = int(data.get('expires_in', 0))
        if not isinstance(token, str) or not token or not 0 < ttl <= 86400 or SCOPE not in data.get('scope', '').split(','):
            raise ValueError()
        if data.get('refresh_token') is not None and not isinstance(data['refresh_token'], str):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, 'TikTok token response did not confirm required authorization') from None
    open_id = data.get('open_id')
    if not isinstance(open_id, str) or not open_id or len(open_id) > 200:
        raise HTTPException(400, 'TikTok did not return a valid account identity')
    result = await provider('GET', 'https://open.tiktokapis.com/v2/user/info/',
        headers={'Authorization': 'Bearer ' + token}, params={'fields': 'open_id,display_name'})
    payload = result.get('data')
    user = payload.get('user') if isinstance(payload, dict) else None
    if not isinstance(user, dict) or user.get('open_id') != open_id or not isinstance(user.get('display_name'), str) or not user['display_name']:
        raise HTTPException(400, 'TikTok profile identity verification failed')
    expected = os.getenv('TIKTOK_EXPECTED_OPEN_ID', '').strip()
    if expected and not secrets.compare_digest(expected, open_id):
        raise HTTPException(409, 'Authorized TikTok account does not match the configured account')
    account = db.query(SocialAccount).filter_by(user_id=db.info['owner_id'], platform='tiktok', account_id=open_id).first()
    if account is None:
        account = SocialAccount(user_id=db.info['owner_id'], platform='tiktok', account_id=open_id,
                                account_name=user['display_name'][:200], account_type='basic_profile', is_mock_mode=False)
        db.add(account)
        db.flush()
    remove_credentials(db, account.user_id, f'account:{account.id}')
    db.flush()
    vault = CredentialStore()
    vault.put(db, account.user_id, f'account:{account.id}', 'access_token', token)
    if data.get('refresh_token'):
        vault.put(db, account.user_id, f'account:{account.id}', 'refresh_token', data['refresh_token'])
    account.account_name = user['display_name'][:200]
    account.scopes = SCOPE
    account.token_expires_at = utcnow()+timedelta(seconds=ttl)
    account.refresh_expires_at = None  # This version requires reconnect on access-token expiry.
    account.connection_status = 'connected'
    account.is_active = True
    account.last_verified_at = utcnow()
    db.commit()
    return RedirectResponse('/tiktok', status_code=303, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@router.get('/accounts')
async def accounts(db: Session = Depends(get_db)):
    rows = db.query(SocialAccount).filter_by(user_id=db.info['owner_id'], platform='tiktok').all()
    return {'real_enabled': False, 'authorization_mode': 'BASIC_PROFILE_ONLY', 'accounts': [
        {'id': row.id, 'display_name': row.account_name, 'external_id': row.account_id,
         'handle_verified': False,
         'connection_status': row.connection_status if row.token_expires_at and row.token_expires_at > utcnow() else 'expired',
         'token_expiry': row.token_expires_at} for row in rows]}


@router.post('/jobs')
async def jobs():
    raise HTTPException(403, 'TikTok REAL publishing is disabled; this integration supports basic-profile connection only')

