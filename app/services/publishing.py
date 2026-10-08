"""Owner-bound durable publishing; only LinkedIn REAL can be explicitly enabled."""
import hashlib
import json
import re
from datetime import timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_
from fastapi import HTTPException
from app.core.security import utcnow, utc_time, safe_error
from app.models.models import ScheduledPost, Campaign, OptimizedContent, SocialAccount
from app.services.platform_adapter import PlatformType, PlatformRegistry, ExecutionMode


def owned(db, model, ident, owner):
    row = db.query(model).filter_by(id=ident, user_id=owner).first()
    if row is None:
        raise HTTPException(404, 'Object not found')
    return row


def prepare_post(db, owner, data, schedule=False):
    try:
        mode = ExecutionMode(data.get('execution_mode'))
        platform = PlatformType(data.get('platform'))
    except ValueError:
        raise HTTPException(400, 'Explicit valid execution_mode and platform required') from None
    if mode == ExecutionMode.REAL:
        if platform == PlatformType.LINKEDIN:
            from app.services.linkedin_channel import real_enabled, validate_account
            enabled = real_enabled()
        elif platform in {PlatformType.FACEBOOK, PlatformType.INSTAGRAM}:
            from app.services.meta_channel import real_enabled, validate_account as meta_validate
            enabled = real_enabled(platform.value)
            validate_account = lambda account: meta_validate(account, db)
        else:
            enabled = False
        if not enabled:
            raise HTTPException(403, 'REAL requires separate platform owner authorization')
        if not data.get('social_account_id'):
            raise HTTPException(400, 'Explicit connected account required')
        try:
            validate_account(owned(db, SocialAccount, data['social_account_id'], owner))
        except ValueError:
            raise HTTPException(400, 'Validated account and scopes required') from None
        if platform == PlatformType.INSTAGRAM and not data.get('_meta_image'):
            raise HTTPException(400, 'Use Meta media job with verified image')
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', data.get('idempotency_key') or ''):
            raise HTTPException(400, 'Stable idempotency_key required for REAL')
    content = data.get('content', '')
    if mode == ExecutionMode.REAL:
        from app.services.sales_copy_store import require_approved
        require_approved(db, owner, data.get('content_id'), platform.value, content, data.get('campaign_id'))
    valid, error = PlatformRegistry.get_adapter(platform, execution_mode=mode).validate_content(content)
    if not valid:
        raise HTTPException(400, error)
    for field, model in [('campaign_id', Campaign), ('content_id', OptimizedContent), ('social_account_id', SocialAccount)]:
        if data.get(field) is not None:
            ref = owned(db, model, data[field], owner)
            if model == SocialAccount and (ref.platform != platform.value or not ref.is_active):
                raise HTTPException(400, 'Account unavailable for this platform')
            if model == OptimizedContent and (ref.platform != platform.value or (data.get('campaign_id') is not None and ref.campaign_id != data['campaign_id'])):
                raise HTTPException(400, 'Content reference mismatch')
    when = utcnow()
    if schedule:
        try:
            when = utc_time(data.get('scheduled_at'))
        except (ValueError, TypeError):
            raise HTTPException(400, 'A timezone-aware scheduled_at is required') from None
        if when <= utcnow():
            raise HTTPException(400, 'Schedule must be in the future')
    fingerprint = hashlib.sha256(json.dumps({'platform':platform.value,'content':content,
        'account':data.get('social_account_id'),'campaign':data.get('campaign_id'),
        'content_id':data.get('content_id'),'mode':mode.value,
        'scheduled_at':when.isoformat() if schedule else None, **({'image':data.get('_meta_image')} if platform.value in {'facebook','instagram'} else {})},sort_keys=True).encode()).hexdigest()
    key = data.get('idempotency_key')
    def existing():
        row = db.query(ScheduledPost).filter_by(user_id=owner,idempotency_key=key).first()
        if row and row.request_fingerprint != fingerprint:
            raise HTTPException(409, 'Idempotency key already used for different content/account/schedule')
        return row
    if key:
        previous = existing()
        if previous:
            return previous
    post = ScheduledPost(user_id=owner, idempotency_key=key, request_fingerprint=fingerprint,
                         source_timezone=data.get('timezone') or (str(data.get('scheduled_at'))[-6:] if schedule else 'UTC'), platform=platform.value, content=content,
                         campaign_id=data.get('campaign_id'), optimized_content_id=data.get('content_id'),
                         social_account_id=data.get('social_account_id'), scheduled_at=when,
                         status='scheduled' if schedule else 'draft', execution_mode=mode.value,
                         is_mock=mode == ExecutionMode.MOCK, attempt_count=0)
    try:
        with db.begin_nested():
            db.add(post)
            db.flush()
    except IntegrityError:
        if not key:
            raise
        previous = existing()
        if not previous:
            raise
        return previous
    if mode == ExecutionMode.REAL and platform.value in {'facebook','instagram'}:
        from app.core.credentials import CredentialStore
        CredentialStore().put(db, owner, f'job:{post.id}', 'meta_payload', json.dumps({'image':data.get('_meta_image')}))
    return post


async def execute_post(db, post):
    try:
        from app.models.models import User
        if not db.query(User).filter_by(id=post.user_id, is_active=True).first():
            raise ValueError('Owner inactive')
        account = None
        if post.social_account_id:
            account = owned(db, SocialAccount, post.social_account_id, post.user_id)
            if not account.is_active or account.platform != post.platform:
                raise ValueError('Account unavailable')
        mode = ExecutionMode(post.execution_mode)
        if mode == ExecutionMode.REAL and (not post.idempotency_key or not post.request_fingerprint):
            raise ValueError('Legacy REAL job requires a new reviewed request')
        adapter = PlatformRegistry.get_adapter(PlatformType(post.platform), execution_mode=mode)
        if mode == ExecutionMode.REAL:
            from app.services.sales_copy_store import require_approved
            require_approved(db, post.user_id, post.optimized_content_id, post.platform, post.content, post.campaign_id)
        result = await adapter.publish(post.content, db=db, account=account, post=post)
        if mode == ExecutionMode.REAL:
            metadata = result.metadata or {}
            post.is_mock = False
            post.next_retry_at = None
            if result.success and not result.is_mock and result.execution_mode == 'REAL' and metadata.get('confirmed') and result.post_id:
                post.status='published';post.platform_post_id=result.post_id;post.url=result.url
                post.published_at=utcnow();post.error_message=None
            elif metadata.get('uncertain') or result.success:
                post.status='reconciliation_required';post.error_message='Provider outcome uncertain; do not retry'
            elif metadata.get('retryable') and post.attempt_count < post.max_attempts:
                post.status='failed_retryable';post.error_message=result.error
                delay=max(30 * 2 ** (post.attempt_count - 1), metadata.get('retry_after',0))
                post.next_retry_at=utcnow()+timedelta(seconds=delay)
            else:
                post.status='failed_final';post.error_message=result.error or 'Publish rejected'
            post.updated_at=utcnow()
            return post_result(post)
        if mode == ExecutionMode.REAL or (mode == ExecutionMode.MOCK and not result.is_mock):
            raise ValueError('Invalid execution result')
        post.status = ('mock_completed' if mode == ExecutionMode.MOCK else 'tested') if result.success else 'failed'
        post.is_mock = mode == ExecutionMode.MOCK
        post.platform_post_id = result.post_id if result.is_mock else None
        post.url = None  # No real post URL or real publication time exists in Phase 1.
        post.published_at = None
        post.error_message = None if result.success else 'Content validation failed'
    except Exception as exc:
        post.status = 'failed_final' if post.execution_mode == 'REAL' else 'failed'
        post.error_message = safe_error(exc)
        post.platform_post_id = post.url = post.published_at = None
    post.updated_at = utcnow()
    return post_result(post)


def post_result(post):
    return dict(success=post.status in {'mock_completed', 'tested', 'scheduled', 'published'}, id=post.id,
                post_id=post.id, platform=post.platform, status=post.status,
                execution_mode=post.execution_mode, is_mock=post.is_mock,
                is_test=post.execution_mode == 'TEST', simulated=post.execution_mode != 'REAL',
                platform_post_id=post.platform_post_id, url=post.url, error=post.error_message,
                published_at=post.published_at, scheduled_at=post.scheduled_at,
                attempt_count=post.attempt_count, last_attempt_at=post.last_attempt_at,
                next_retry_at=post.next_retry_at, idempotency_key=post.idempotency_key, timezone=post.source_timezone)


async def process_post(db, post, allowed=('draft',)):
    ident, owner = post.id, post.user_id
    due = or_(ScheduledPost.status=='draft', and_(ScheduledPost.status=='scheduled',ScheduledPost.scheduled_at<=utcnow()), and_(ScheduledPost.status=='failed_retryable',ScheduledPost.next_retry_at<=utcnow()))
    claimed = db.query(ScheduledPost).filter(due, ScheduledPost.id==ident, ScheduledPost.user_id==owner,
        ScheduledPost.status.in_(allowed), ScheduledPost.attempt_count < ScheduledPost.max_attempts).update({
            'status':'processing','attempt_count':ScheduledPost.attempt_count+1,
            'last_attempt_at':utcnow(),'updated_at':utcnow()},synchronize_session=False)
    db.commit()  # Durable job + claim before any external request.
    db.expire_all()
    post = owned(db, ScheduledPost, ident, owner)
    if claimed:
        await execute_post(db, post)
        db.commit()
    return post_result(post)


async def immediate(db, owner, data):
    post = prepare_post(db, owner, data)
    return await process_post(db, post)
