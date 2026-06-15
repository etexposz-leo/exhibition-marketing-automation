"""
Authentication routes for login, register, logout.
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.auth import (
    authenticate_user, 
    create_user, 
    get_user_by_email,
    get_user_by_id
)


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    company_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """Get current user from session. Raises 401 if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {"id": user.id, "email": user.email, "username": user.username, "company_name": user.company_name}


@router.post("/register")
async def register(
    request: Request,
    reg_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """Register a new user."""
    # Check if email already exists
    existing = get_user_by_email(db, reg_data.email)
    if existing:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Email already registered"}
        )
    
    # Validate password
    if len(reg_data.password) < 6:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Password must be at least 6 characters"}
        )
    
    # Create user
    user = create_user(
        db=db,
        email=reg_data.email,
        username=reg_data.username,
        password=reg_data.password,
        company_name=reg_data.company_name
    )
    
    # Set session
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["username"] = user.username
    
    return {
        "success": True,
        "message": "Registration successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "company_name": user.company_name
        }
    }


@router.post("/login")
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Login user."""
    user = authenticate_user(db, login_data.email, login_data.password)
    
    if not user:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Invalid email or password"}
        )
    
    # Set session
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["username"] = user.username
    request.session["company_name"] = user.company_name
    
    return {
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "company_name": user.company_name
        }
    }


@router.post("/logout")
async def logout(request: Request):
    """Logout user."""
    request.session.clear()
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    return {
        "success": True,
        "user": user
    }


@router.get("/check")
async def check_auth(request: Request):
    """Check if user is authenticated."""
    user_id = request.session.get("user_id")
    if user_id:
        return {
            "authenticated": True,
            "user_id": user_id,
            "email": request.session.get("user_email"),
            "username": request.session.get("username")
        }
    return {"authenticated": False}
