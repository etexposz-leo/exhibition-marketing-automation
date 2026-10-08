"""Owner-bound OAuth state and member identity binding. Does not publish."""
import os
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.credentials import CredentialStore, remove_credentials
from app.core.security import utcnow
from app.models.models import SocialAccount, OAuthAttempt, ScheduledPost, CredentialMetadata, CredentialSecret
from app.services import linkedin_channel as channel

router = APIRouter(prefix='/linkedin', tags=['linkedin'])


def owned_account(db, ident):
    row = db.query(SocialAccount).filter_by(id=ident, user_id=db.info['owner_id'], platform='linkedin').first()
    if not row:
        raise HTTPException(404, 'Account not found')
    return row


def same_origin(request, local_only=False):
    origin = request.headers.get('origin')
    expected = urlsplit(os.getenv('LINKEDIN_REDIRECT_URI', '') if local_only else channel.oauth_config()['REDIRECT_URI'])
    if not origin or origin != f'{expected.scheme}://{expected.netloc}':
        raise HTTPException(403, 'Same-origin request required')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@router.post('/oauth/start')
async def start(request: Request, db: Session = Depends(get_db)):
    same_origin(request)
    cfg = channel.oauth_config()
    state = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    request.session['linkedin_nonce'] = nonce
    db.add(OAuthAttempt(user_id=db.info['owner_id'], state_hash=digest(state), browser_hash=digest(nonce),
                        expires_at=utcnow()+timedelta(minutes=10)))
    db.commit()
    return {'authorization_url': 'https://www.linkedin.com/oauth/v2/authorization?' + urlencode({
        'response_type':'code', 'client_id':cfg['CLIENT_ID'], 'redirect_uri':cfg['REDIRECT_URI'],
        'state':state, 'scope':' '.join(sorted(channel.SCOPES))})}


async def token_response(form):
    try:
        response = await channel.http.request('POST', 'https://www.linkedin.com/oauth/v2/accessToken', data=form)
        if response.status_code != 200:
            raise ValueError()
        data = response.json()
        if not isinstance(data.get('access_token'), str) or int(data.get('expires_in', 0)) <= 0:
            raise ValueError()
        return data
    except Exception:
        raise HTTPException(400, 'LinkedIn token operation failed; reauthorize') from None


async def verified_identity(token):
    try:
        response = await channel.http.request('GET', 'https://api.linkedin.com/v2/userinfo',
                                              headers={'Authorization': 'Bearer ' + token})
        data = response.json()
        import re
        if response.status_code != 200 or not re.fullmatch(r'[A-Za-z0-9_-]+', data.get('sub', '')) or not data.get('name'):
            raise ValueError()
        return 'urn:li:person:' + data['sub'], data['name'][:200]
    except Exception:
        raise HTTPException(400, 'LinkedIn identity verification failed') from None


def store_tokens(db, account, data, *, refresh=False):
    scopes = set(data.get('scope', '').replace(',', ' ').split())
    if not channel.SCOPES.issubset(scopes):
        raise HTTPException(400, 'LinkedIn did not confirm required scopes')
    vault = CredentialStore()
    vault.put(db, account.user_id, f'account:{account.id}', 'access_token', data['access_token'])
    if data.get('refresh_token'):
        ttl = int(data.get('refresh_token_expires_in', 0))
        if ttl > 0:
            vault.put(db, account.user_id, f'account:{account.id}', 'refresh_token', data['refresh_token'])
            expiry = utcnow()+timedelta(seconds=ttl)
            account.refresh_expires_at = min(account.refresh_expires_at, expiry) if refresh and account.refresh_expires_at else expiry
    account.token_expires_at = utcnow()+timedelta(seconds=int(data['expires_in']))
    account.scopes = ' '.join(sorted(scopes))
    account.connection_status = 'connected'
    account.last_verified_at = utcnow()
    account.is_active = True


@router.get('/oauth/callback')
async def callback(request: Request, state: str = '', code: str = '', error: str = '', db: Session = Depends(get_db)):
    nonce = request.session.pop('linkedin_nonce', '')
    attempt = db.query(OAuthAttempt).filter_by(state_hash=digest(state), user_id=db.info['owner_id']).first()
    if not nonce or not attempt or not secrets.compare_digest(attempt.browser_hash, digest(nonce)):
        raise HTTPException(403, 'Invalid OAuth state')
    consumed = db.query(OAuthAttempt).filter(OAuthAttempt.id == attempt.id, OAuthAttempt.consumed == False,
        OAuthAttempt.expires_at > utcnow()).update({'consumed':True}, synchronize_session=False)
    db.commit()
    if not consumed:
        raise HTTPException(403, 'OAuth state expired or already consumed')
    if error or not code:
        raise HTTPException(400, 'LinkedIn authorization was not completed')
    cfg = channel.oauth_config()
    data = await token_response({'grant_type':'authorization_code','code':code,'client_id':cfg['CLIENT_ID'],
                                'client_secret':cfg['CLIENT_SECRET'],'redirect_uri':cfg['REDIRECT_URI']})
    urn, name = await verified_identity(data['access_token'])
    account = db.query(SocialAccount).filter_by(platform='linkedin', account_id=urn, user_id=db.info['owner_id']).first()
    if account is None:
        account = SocialAccount(user_id=db.info['owner_id'], platform='linkedin', account_id=urn, account_name=name,
                                account_type='member', is_mock_mode=False)
        db.add(account)
        db.flush()
    account.account_name = name
    account.account_type = 'member'
    # A new authorization must not retain an earlier refresh token.
    remove_credentials(db, account.user_id, f'account:{account.id}')
    db.flush()
    account.refresh_expires_at = None
    store_tokens(db, account, data)
    db.commit()
    return RedirectResponse('/linkedin', status_code=303, headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@router.get('/accounts')
async def accounts(db: Session = Depends(get_db)):
    rows = db.query(SocialAccount).filter_by(platform='linkedin').all()
    def lifecycle(a):
        kinds = {r[0] for r in db.query(CredentialMetadata.kind).join(
            CredentialSecret, (CredentialSecret.credential_id == CredentialMetadata.id)
            & (CredentialSecret.user_id == CredentialMetadata.user_id)).filter(
                CredentialMetadata.user_id == a.user_id, CredentialMetadata.scope == f'account:{a.id}').all()}
        state = channel.token_lifecycle(a, has_access='access_token' in kinds)
        refresh_available = bool(a.is_active and a.connection_status == 'connected' and 'refresh_token' in kinds
                                 and a.refresh_expires_at and a.refresh_expires_at > utcnow())
        messages = {
            'CONNECTED': 'Connected. ' + ('Refresh is available.' if refresh_available else 'Automatic refresh unavailable; reconnect with OAuth before expiry.'),
            'TOKEN_EXPIRING': 'Token expires within 7 days. ' + ('Refresh or reconnect with OAuth.' if refresh_available else 'Reconnect with OAuth; no refresh token was issued.'),
            'REAUTH_REQUIRED': 'Authorization is unavailable or expired. Reconnect with OAuth.',
            'DISCONNECTED': 'Disconnected. Connect with OAuth to authorize this account.',
        }
        return {'token_status': state, 'reauth_required': state == 'REAUTH_REQUIRED',
                'lifecycle_message': messages[state], 'refresh_available': refresh_available}
    return {'real_enabled':channel.real_enabled(), 'accounts':[{
        'id':a.id, 'platform':a.platform, 'external_id':a.account_id, 'display_name':a.account_name,
        'account_type':a.account_type, 'owner_user_id':a.user_id,
        'connection_status':('expired' if a.token_expires_at and a.token_expires_at <= utcnow() and a.connection_status=='connected' else a.connection_status),
        'scopes':(a.scopes or '').split(), 'token_expiry':a.token_expires_at,
        'last_verified_at':a.last_verified_at, **lifecycle(a)
    } for a in rows]}


@router.post('/accounts/{account_id}/refresh')
async def refresh(account_id: int, request: Request, db: Session = Depends(get_db)):
    same_origin(request)
    account = owned_account(db, account_id)
    if account.connection_status != 'connected' or not account.refresh_expires_at or account.refresh_expires_at <= utcnow():
        raise HTTPException(409, 'Programmatic refresh unavailable; reconnect with OAuth')
    cfg = channel.oauth_config()
    token = CredentialStore().get(db, account.user_id, f'account:{account.id}', 'refresh_token')
    data = await token_response({'grant_type':'refresh_token','refresh_token':token,
                                'client_id':cfg['CLIENT_ID'],'client_secret':cfg['CLIENT_SECRET']})
    urn, _ = await verified_identity(data['access_token'])
    if urn != account.account_id:
        raise HTTPException(400, 'LinkedIn identity changed; reconnect')
    store_tokens(db, account, data, refresh=True)
    db.commit()
    return {'success':True,'connection_status':account.connection_status}


@router.post('/accounts/{account_id}/disconnect')
async def disconnect(account_id: int, request: Request, db: Session = Depends(get_db)):
    same_origin(request, local_only=True)
    account = owned_account(db, account_id)
    if db.query(ScheduledPost).filter(ScheduledPost.social_account_id==account_id, ScheduledPost.status=='processing').first():
        raise HTTPException(409, 'In-flight job requires reconciliation before disconnect')
    remove_credentials(db, account.user_id, f'account:{account.id}')
    account.connection_status='disconnected';account.is_active=False
    db.query(ScheduledPost).filter(ScheduledPost.social_account_id==account_id,
        ScheduledPost.status.in_(['draft','scheduled','failed_retryable'])).update({'status':'cancelled'})
    db.commit()
    return {'success':True,'local_credentials_removed':True,'remote_revocation':'OWNER_ACTION_REQUIRED',
            'message':'Remove this app in LinkedIn Settings > Data privacy > Permitted services. Remote revocation is not claimed.'}
