"""Approval-ready local handoff integrated with existing campaigns and encrypted store.

No provider transport, OAuth imitation, scheduled dispatch or publish method exists here.
New provider onboarding remains explicitly blocked until official entitlement is verified.
"""
import base64
import hashlib
import io
import json
import os
import uuid
import zipfile
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.credentials import CredentialStore
from app.core.security import utcnow, utc_time
from app.models.models import Campaign, OptimizedContent, ScheduledPost, SocialAccount
from app.services.channel_capabilities import CHANNELS, NEW_CHANNELS
from app.services.publishing import owned

router = APIRouter(prefix='/channels', tags=['six-channel workspace'])


def origin(request):
    expected = os.getenv('CHANNEL_WORKSPACE_ORIGIN', 'https://localhost:18421')
    if request.headers.get('origin') != expected:
        raise HTTPException(403, 'Same-origin request required')


def owner(db):
    return db.info['owner_id']


def new_channel(platform):
    if platform not in NEW_CHANNELS:
        raise HTTPException(404, 'New handoff channel not found')


@router.get('')
def overview(db: Session = Depends(get_db)):
    result = []
    for platform, capability in CHANNELS.items():
        accounts = db.query(SocialAccount).filter_by(user_id=owner(db), platform=platform).all()
        safe = []
        for a in accounts:
            encrypted = False
            try:
                encrypted = bool(CredentialStore().get(db, owner(db), f'account:{a.id}', 'access_token'))
            except ValueError:
                pass
            bound = a.is_active and a.connection_status == 'connected' and not a.is_mock_mode
            safe.append(dict(id=a.id, name=a.account_name, external_id=a.account_id,
                ACCOUNT_BOUND=bool(bound), TOKEN_VALID=bool(bound and encrypted and a.token_expires_at and a.token_expires_at > utcnow()+timedelta(seconds=60)),
                token_expiry=a.token_expires_at, last_check=a.last_verified_at,
                scopes=(a.scopes or '').split(), TOKEN_ENCRYPTED=encrypted))
        last = db.query(ScheduledPost).filter_by(user_id=owner(db), platform=platform).order_by(ScheduledPost.id.desc()).first()
        result.append(dict(platform=platform, **capability, accounts=safe,
            ACCOUNT_BOUND=any(a['ACCOUNT_BOUND'] for a in safe), TOKEN_VALID=any(a['TOKEN_VALID'] for a in safe),
            PUBLISH_SUPPORTED=platform not in NEW_CHANNELS,
            REAL_PUBLISH_ENABLED=False if platform in NEW_CHANNELS else os.getenv(platform.upper()+'_REAL_PUBLISH_ENABLED') == 'true',
            LAST_POST_STATUS=last.status if last else 'NONE',
            MANUAL_PUBLISH_HANDOFF_REQUIRED=platform in NEW_CHANNELS))
    return {'channels': result, 'total': 6, 'provider_contacted': False}


@router.post('/{platform}/connect')
def connect(platform: str, request: Request):
    origin(request); new_channel(platform)
    raise HTTPException(409, CHANNELS[platform]['blocker'])


@router.post('/{platform}/reconnect')
def reconnect(platform: str, request: Request):
    return connect(platform, request)


@router.post('/{platform}/disconnect')
def disconnect(platform: str, request: Request, db: Session = Depends(get_db)):
    origin(request); new_channel(platform)
    # Do not delete or simulate revocation for a future provider implementation.
    if db.query(SocialAccount).filter_by(user_id=owner(db), platform=platform, is_active=True).first():
        raise HTTPException(409, 'Use the verified provider revocation implementation; no account was changed')
    return {'disconnected': True, 'provider_contacted': False, 'account_was_bound': False}


@router.get('/campaigns')
def campaigns(db: Session = Depends(get_db)):
    return [{'id': c.id, 'name': c.campaign_name or c.exhibition_name} for c in db.query(Campaign).filter_by(user_id=owner(db)).all()]


class NewCampaign(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(default='Exhibitions', max_length=200)


@router.post('/campaigns')
def campaign(body: NewCampaign, request: Request, db: Session = Depends(get_db)):
    origin(request)
    row = Campaign(user_id=owner(db), campaign_name=body.name, exhibition_name=body.name,
        customer_industry=body.industry, selected_platforms=json.dumps(list(CHANNELS)))
    db.add(row); db.flush() if db.info.get('original_draft_transaction') else db.commit()
    return {'id': row.id}


class Variant(BaseModel):
    title: str = Field(default='', max_length=200)
    caption: str = Field(min_length=1, max_length=10000)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    cover_id: str | None = None
    recommended_publish_time: str | None = None


def asset(db, ident):
    try:
        if str(uuid.UUID(ident)) != ident: raise ValueError()
        return json.loads(CredentialStore().get(db, owner(db), 'channel-asset:'+ident, 'media'))
    except (ValueError, TypeError):
        raise HTTPException(404, 'Media not found') from None


@router.post('/media')
async def media(request: Request, db: Session = Depends(get_db)):
    origin(request)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 16 * 1024 * 1024: raise HTTPException(413, 'Local handoff limit: 16 MiB per asset')
    typ = request.headers.get('content-type', '').split(';')[0]
    valid = {'image/png': data.startswith(b'\x89PNG\r\n\x1a\n'),
        'image/jpeg': data.startswith(b'\xff\xd8\xff'),
        'video/mp4': len(data) > 12 and data[4:8] == b'ftyp'}
    if not valid.get(typ): raise HTTPException(400, 'PNG/JPEG/MP4 signature required')
    ident = str(uuid.uuid4())
    ext = {'image/png':'png','image/jpeg':'jpg','video/mp4':'mp4'}[typ]
    value = dict(name=ident+'.'+ext, mime=typ, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
        data=base64.b64encode(data).decode())
    CredentialStore().put(db, owner(db), 'channel-asset:'+ident, 'media', json.dumps(value))
    db.commit()
    return {'id': ident, 'bytes': len(data), 'media_type': typ, 'provider_uploaded': False}


@router.get('/media/{ident}')
def preview_media(ident: str, db: Session = Depends(get_db)):
    value = asset(db, ident)
    return Response(base64.b64decode(value['data']), media_type=value['mime'], headers={
        'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"default-src 'none'; media-src 'self'; sandbox"})


def variants(db, campaign_id, platform):
    owned(db, Campaign, campaign_id, owner(db)); new_channel(platform)
    return db.query(OptimizedContent).filter_by(user_id=owner(db), campaign_id=campaign_id, platform=platform)


@router.get('/campaigns/{campaign_id}/{platform}')
def load(campaign_id: int, platform: str, db: Session = Depends(get_db)):
    row = variants(db, campaign_id, platform).order_by(OptimizedContent.id.desc()).first()
    return {'id': row.id, **json.loads(row.changes)} if row else None


@router.post('/campaigns/{campaign_id}/{platform}')
def save(campaign_id: int, platform: str, body: Variant, request: Request, db: Session = Depends(get_db)):
    origin(request); variants(db, campaign_id, platform)
    payload = body.model_dump()
    if body.recommended_publish_time:
        try: utc_time(body.recommended_publish_time)
        except ValueError: raise HTTPException(400, 'Recommended time needs a timezone') from None
    if any(len(tag)>100 or '\n' in tag for tag in body.hashtags): raise HTTPException(400, 'Invalid hashtag')
    assets = [asset(db, x) for x in body.asset_ids]
    if body.cover_id and not asset(db, body.cover_id)['mime'].startswith('image/'):
        raise HTTPException(400, 'Cover must be an image')
    warnings = []
    if not assets: warnings.append('Media required before approval; no image/video has been supplied.')
    if platform in {'tiktok','douyin'} and assets and (len(assets)!=1 or assets[0]['mime']!='video/mp4'):
        raise HTTPException(400, 'This local video handoff requires one MP4; confirm vertical format in preview')
    if platform == 'xiaohongshu' and assets:
        if any(a['mime']=='video/mp4' for a in assets) and (len(assets)!=1 or assets[0]['mime']!='video/mp4'):
            raise HTTPException(400, 'Choose an image carousel OR one video')
    if platform == 'xiaohongshu' and not body.title.strip(): warnings.append('RED title required before approval.')
    payload['warnings'] = warnings
    payload['status'] = 'DRAFT'
    payload['fingerprint'] = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    row = OptimizedContent(user_id=owner(db), campaign_id=campaign_id, platform=platform,
        original_content=body.caption, optimized_content=body.caption, changes=json.dumps(payload,ensure_ascii=False),
        warnings=json.dumps(warnings), character_count=len(body.caption), character_limit=10000)
    db.add(row); db.flush() if db.info.get('original_draft_transaction') else db.commit()
    return {'id': row.id, **payload}


class Approval(BaseModel):
    fingerprint: str
    media_reviewed: bool = False


def draft(db, ident):
    row = owned(db, OptimizedContent, ident, owner(db)); new_channel(row.platform)
    try: payload = json.loads(row.changes)
    except (ValueError, TypeError): raise HTTPException(400,'Not a handoff draft') from None
    latest = variants(db,row.campaign_id,row.platform).order_by(OptimizedContent.id.desc()).first()
    if latest.id != ident: raise HTTPException(409, 'Draft superseded; review latest version')
    return row, payload


@router.post('/drafts/{ident}/approve')
def approve(ident: int, body: Approval, request: Request, db: Session = Depends(get_db)):
    origin(request); row, payload = draft(db, ident)
    if payload['fingerprint'] != body.fingerprint: raise HTTPException(409, 'Content changed')
    if payload['warnings'] or not body.media_reviewed: raise HTTPException(400, 'Resolve warnings and review media first')
    CredentialStore().put(db,owner(db),f'channel-draft:{ident}','approval',json.dumps(dict(
        fingerprint=body.fingerprint, approved_at=utcnow().isoformat(), owner=owner(db), purpose='MANUAL_PACKAGE_ONLY')))
    db.commit()
    return {'status':'APPROVED_MANUAL_PACKAGE', 'real_publish_authorized':False}


@router.get('/drafts/{ident}/package')
def package(ident: int, db: Session = Depends(get_db)):
    row, payload = draft(db, ident)
    try: approval = json.loads(CredentialStore().get(db,owner(db),f'channel-draft:{ident}','approval'))
    except ValueError: raise HTTPException(409,'Owner approval required for export') from None
    if approval['fingerprint'] != payload['fingerprint']: raise HTTPException(409,'Approval stale')
    text = '\n\n'.join(x for x in [payload['title'],payload['caption'], ' '.join('#'+x.lstrip('#') for x in payload['hashtags'])] if x)
    buffer = io.BytesIO()
    manifest = {**payload, 'channel':row.platform,'campaign_id':row.campaign_id,'draft_id':ident,
        'status':'APPROVED_MANUAL_PACKAGE','published':False,'scheduled_automatically':False, 'approval':approval}
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('copy-ready.txt',text)
        for ident in dict.fromkeys(payload['asset_ids'] + ([payload['cover_id']] if payload['cover_id'] else [])):
            value=asset(db,ident)
            z.writestr('media/'+value['name'],base64.b64decode(value['data']))
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        z.writestr('README.txt','Owner must publish manually. This export does not upload, schedule or publish. Review native platform limits, music/media rights, cover and visibility before posting. Media signature checks are not full codec/vertical-format validation.')
    return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{row.platform}-draft-{row.id}.zip"','Cache-Control':'no-store'})
