"""
Authentication dependencies for FastAPI routes.
"""

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.models.models import User


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
