"""Request-scoped ORM isolation, including bulk mutations and reference validation."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, with_loader_criteria
from app.core.database import Base, get_db


def authenticated_session(request: Request, db: Session = Depends(get_db)):
    from app.core.dependencies import get_current_user
    user = get_current_user(request, db)
    db.info['owner_id'] = user['id']
    import os
    if os.getenv('MARKETING_LOCAL_AUTH')=='true' and not request.url.path.startswith('/api/marketing/modules/'):
        from app.core.module_access import require
        require(db,'MARKETING_ACCESS')
    return user['id']


@event.listens_for(Session, 'do_orm_execute')
def isolate_queries(state):
    owner = state.session.info.get('owner_id')
    if owner is None:
        return
    if state.is_select:
        for mapper in Base.registry.mappers:
            model = mapper.class_
            if hasattr(model, 'user_id'):
                state.statement = state.statement.options(with_loader_criteria(model, model.user_id == owner, include_aliases=True))
    elif state.is_update or state.is_delete:
        mapper = state.bind_arguments.get('mapper')
        if mapper and hasattr(mapper.class_, 'user_id'):
            state.statement = state.statement.where(mapper.class_.user_id == owner)


@event.listens_for(Session, 'before_flush')
def protect_mutations(db, context, instances):
    from app.models.models import SocialAccount, Campaign, GeneratedContent, OptimizedContent, CredentialMetadata
    owner = db.info.get('owner_id')
    for obj in db.new | db.dirty | db.deleted:
        if isinstance(obj, SocialAccount):
            for field in ('access_token', 'refresh_token', 'api_key'):
                if inspect(obj).attrs[field].history.added and getattr(obj, field):
                    raise ValueError('Plaintext credential writes are forbidden')
        if owner is None or not hasattr(obj, 'user_id'):
            continue
        if obj in db.new and obj.user_id is None:
            obj.user_id = owner
        if obj.user_id != owner:
            raise HTTPException(404, 'Object not found')
        refs = [('campaign_id', Campaign), ('social_account_id', SocialAccount),
                ('optimized_content_id', OptimizedContent), ('credential_id', CredentialMetadata)]
        if isinstance(obj, OptimizedContent):
            refs.append(('content_id', GeneratedContent))
        for field, model in refs:
            ident = getattr(obj, field, None)
            # Legacy invalid references must not prevent persisting a quarantined
            # failure. Validate newly assigned references; the executor validates
            # every existing account again before using it.
            changed = field in inspect(obj).attrs and inspect(obj).attrs[field].history.has_changes()
            if ident is not None and (obj in db.new or changed):
                ref = db.query(model).filter_by(id=ident, user_id=owner).first()
                if ref is None:
                    raise HTTPException(404, 'Referenced object not found')
                if field == 'social_account_id' and getattr(obj, 'platform', ref.platform) != ref.platform:
                    raise HTTPException(400, 'Account platform mismatch')
                if field == 'optimized_content_id' and obj.campaign_id is not None and ref.campaign_id != obj.campaign_id:
                    raise HTTPException(400, 'Content campaign mismatch')
