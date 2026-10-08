"""Read-only grouped destination and batch preflight. No publishing transport.

Until additional provider connectors are implemented and accepted this endpoint
must fail closed, even when someone changes an environment switch externally.
"""
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.api.channel_workspace import origin, asset
from app.core.database import get_db
from app.core.module_access import require
from app.models.models import Campaign, SocialAccount, OptimizedContent
from app.services.publishing import owned
from app.services.publishing_catalog import CATALOG, catalog
from app.services.sales_copy_store import require_approved

router = APIRouter(prefix='/marketing/publishing-center', tags=['Publishing center'])


@router.get('/catalog')
def destinations(db: Session = Depends(get_db)):
    who = require(db, 'MARKETING_ACCESS')
    rows = catalog()
    accounts = db.query(SocialAccount).filter_by(user_id=who).all()
    for row in rows:
        row['accounts'] = [dict(id=a.id, name=a.account_name,
            connection_status=a.connection_status, active=a.is_active)
            for a in accounts if a.platform == row['id']]
    return dict(channels=rows, groups=[dict(id='international', name='国际平台'),
        dict(id='china', name='中国平台')], total=len(rows),
        real_enabled=False, batch_execution_enabled=False,
        provider_contacted=False, account_status_source='local_database_not_live_validation')


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid')
    platform: str
    content: str = Field(min_length=1, max_length=30000)
    social_account_id: int | None = None
    content_id: int | None = None
    asset_ids: list[str] = Field(default_factory=list, max_length=20)


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    campaign_id: int
    targets: list[Target] = Field(min_length=1, max_length=21)
    execution_mode: Literal['TEST'] = 'TEST'


@router.post('/preview')
def preview(body: Preview, request: Request, db: Session = Depends(get_db)):
    origin(request)
    who = require(db, 'MARKETING_ACCESS')
    owned(db, Campaign, body.campaign_id, who)
    names = [item.platform for item in body.targets]
    if len(set(names)) != len(names):
        raise HTTPException(422, 'Each platform must occur once; RED and Xiaohongshu are one destination')
    if any(name not in CATALOG for name in names):
        raise HTTPException(422, 'Unknown platform')
    results = []
    for item in body.targets:
        info = CATALOG[item.platform]
        blockers = ['REAL_DISABLED', 'BATCH_EXECUTION_NOT_IMPLEMENTED']
        if info['transport_status'] != 'IMPLEMENTED':
            blockers.append('PROVIDER_CONNECTOR_NOT_IMPLEMENTED')
        if item.platform == 'tiktok':
            blockers.append('INTERNAL_USE_NOT_ELIGIBLE')
        if item.social_account_id is None:
            blockers.append('ACCOUNT_NOT_SELECTED')
        else:
            account = owned(db, SocialAccount, item.social_account_id, who)
            if account.platform != item.platform:
                raise HTTPException(422, 'Account does not match platform')
            if not account.is_active or account.connection_status != 'connected' or account.is_mock_mode:
                blockers.append('ACCOUNT_NOT_CONNECTED')
            else:
                blockers.append('LIVE_ACCOUNT_PERMISSION_CHECK_REQUIRED')
        media = [asset(db, ident) for ident in item.asset_ids]
        has_image = any(m['mime'].startswith('image/') for m in media)
        has_video = any(m['mime'].startswith('video/') for m in media)
        need = info['media_requirement']
        if need == 'video' and not has_video:
            blockers.append('VIDEO_REQUIRED')
        if need == 'image' and not has_image:
            blockers.append('IMAGE_REQUIRED')
        if need == 'image_or_video' and not (has_image or has_video):
            blockers.append('IMAGE_OR_VIDEO_REQUIRED')
        if item.content_id is None:
            blockers.append('APPROVED_SALES_COPY_REQUIRED')
        else:
            owned(db, OptimizedContent, item.content_id, who)
            try:
                require_approved(db, who, item.content_id, item.platform, item.content, body.campaign_id)
            except HTTPException:
                blockers.append('EXACT_SALES_COPY_APPROVAL_REQUIRED')
        results.append(dict(platform=item.platform, name=info['name'], region=info['region'],
            status='BLOCKED', blockers=blockers, content=item.content,
            account_id=item.social_account_id, asset_ids=item.asset_ids,
            owner_action=info['owner_action'], external_post_id=None, url=None))
    fingerprint = hashlib.sha256(json.dumps(dict(owner=who, **body.model_dump()),
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(status='PREFLIGHT_ONLY', fingerprint=fingerprint, results=results,
        execution_mode='TEST', provider_contacted=False, published=False,
        scheduled=False, real_enabled=False)


@router.post('/publish')
def publish(request: Request, db: Session = Depends(get_db)):
    origin(request)
    require(db, 'MARKETING_ACCESS')
    raise HTTPException(403, 'REAL disabled. Batch delivery is not implemented or authorized; no content was sent.')
