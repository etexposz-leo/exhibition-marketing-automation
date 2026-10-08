"""
Authentication dependencies for FastAPI routes.
"""

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.models.models import User


def require_verified_session(request: Request) -> int:
    """Router-level session check; authenticated_session also checks DB identity."""
    from app.core.cloud_runtime import enabled
    user_id = request.session.get('user_id')
    if not user_id:
        raise HTTPException(401, 'Not authenticated')
    if not request.session.get('mfa_verified' if enabled() else 'sms_verified'):
        raise HTTPException(403, 'Additional verification required')
    return user_id


def get_current_user(request: Request, db: Session) -> dict:
    """
    Get current user from session.
    Raises 401 if not authenticated.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    from app.core.cloud_runtime import enabled
    if enabled() and (user.is_demo or not request.session.get('mfa_verified')):
        raise HTTPException(status_code=403, detail='Cloud MFA sign-in required')
    
    import os
    if os.getenv('MARKETING_LOCAL_AUTH')=='true':
        from app.core.module_access import profile
        access=profile(db,user.id)
        if access['locked'] or request.session.get('module_session_version',0)!=access['session_version']:
            raise HTTPException(401,'Session expired or account locked; sign in again')
    return {"id": user.id, "email": user.email, "username": user.username, "company_name": user.company_name}


def get_optional_user(request: Request, db: Session) -> Optional[dict]:
    """
    Get current user from session if authenticated.
    Returns None if not authenticated.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return None
    
    return {"id": user.id, "email": user.email, "username": user.username, "company_name": user.company_name}
