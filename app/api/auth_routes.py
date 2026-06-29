"""
Authentication routes for login, register, logout, and SMS verification.
"""
import os

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.auth import (
    authenticate_user, 
    create_user, 
    get_user_by_email,
    get_user_by_id
)
from app.models.models import User, SMSVerification
from app.services.sms_service import get_provider, generate_verification_code, hash_code, verify_code


router = APIRouter(prefix="/auth", tags=["auth"])

# SMS configuration
SMS_CODE_EXPIRY_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5
DEMO_VERIFICATION_CODE = "123456"


def is_mock_mode() -> bool:
    """Check if running in mock SMS mode."""
    return os.environ.get("SMS_MOCK_MODE", "true").lower() == "true"


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    company_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class SendSMSRequest(BaseModel):
    phone_number: str


class VerifySMSRequest(BaseModel):
    phone_number: str
    code: str


def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """Get current user from session. Raises 401 if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {"id": user.id, "email": user.email, "username": user.username, "company_name": user.company_name}


def require_sms_verified(request: Request, db: Session = Depends(get_db)) -> dict:
    """Require user to have verified their phone via SMS."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if SMS is verified in session
    if not request.session.get("sms_verified"):
        raise HTTPException(status_code=403, detail="Phone verification required")
    
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
    
    # Set session (but not sms_verified yet)
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["username"] = user.username
    request.session["sms_verified"] = False
    
    return {
        "success": True,
        "message": "Registration successful. Phone verification required.",
        "requires_verification": True,
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
    """Login user. Requires SMS verification after successful login."""
    user = authenticate_user(db, login_data.email, login_data.password)
    
    if not user:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Invalid email or password"}
        )
    
    # Check if phone is already verified for this user
    if user.phone_verified and user.sms_verified_at:
        # Skip SMS verification if already verified
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email
        request.session["username"] = user.username
        request.session["company_name"] = user.company_name
        request.session["sms_verified"] = True
        
        return {
            "success": True,
            "message": "Login successful",
            "requires_verification": False,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "company_name": user.company_name
            }
        }
    
    # Set session (but not sms_verified yet)
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["username"] = user.username
    request.session["company_name"] = user.company_name
    request.session["sms_verified"] = False
    
    return {
        "success": True,
        "message": "Login successful. Phone verification required.",
        "requires_verification": True,
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
    """Check if user is authenticated and SMS verified."""
    user_id = request.session.get("user_id")
    sms_verified = request.session.get("sms_verified", False)
    
    if user_id:
        return {
            "authenticated": True,
            "sms_verified": sms_verified,
            "user_id": user_id,
            "email": request.session.get("user_email"),
            "username": request.session.get("username"),
            "mock_mode": is_mock_mode()
        }
    return {"authenticated": False, "sms_verified": False, "mock_mode": is_mock_mode()}


@router.post("/send-sms-code")
async def send_sms_code(
    request: Request,
    sms_data: SendSMSRequest,
    db: Session = Depends(get_db)
):
    """Send SMS verification code to user's phone."""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Not authenticated"}
        )
    
    user = get_user_by_id(db, user_id)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "User not found"}
        )
    
    # Clean up old verification codes for this user
    db.query(SMSVerification).filter(
        SMSVerification.user_id == user_id
    ).delete()
    
    # Generate new code - use demo code in mock mode
    if is_mock_mode():
        code = DEMO_VERIFICATION_CODE
    else:
        code = generate_verification_code()
    code_hash = hash_code(code)
    expires_at = datetime.utcnow() + timedelta(minutes=SMS_CODE_EXPIRY_MINUTES)
    
    # Store verification record
    verification = SMSVerification(
        user_id=user_id,
        phone_number=sms_data.phone_number,
        code_hash=code_hash,
        expires_at=expires_at
    )
    db.add(verification)
    
    # Update user's phone number
    user.phone_number = sms_data.phone_number
    db.commit()
    
    # Send SMS
    sms_provider = get_provider()
    message = f"Your BoothOS verification code is: {code}"
    
    if sms_provider.send_sms(sms_data.phone_number, message):
        return {
            "success": True,
            "message": "Verification code sent",
            "expires_in_minutes": SMS_CODE_EXPIRY_MINUTES
        }
    else:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Failed to send SMS"}
        )


@router.post("/verify-sms-code")
async def verify_sms_code(
    request: Request,
    verify_data: VerifySMSRequest,
    db: Session = Depends(get_db)
):
    """Verify SMS code and enable full access."""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Not authenticated"}
        )
    
    user = get_user_by_id(db, user_id)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "User not found"}
        )
    
    # Find valid verification record
    verification = db.query(SMSVerification).filter(
        SMSVerification.user_id == user_id,
        SMSVerification.phone_number == verify_data.phone_number,
        SMSVerification.verified_at == None,
        SMSVerification.expires_at > datetime.utcnow()
    ).order_by(SMSVerification.created_at.desc()).first()
    
    if not verification:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "No valid verification code found. Please request a new code."}
        )
    
    # Check attempt limit
    if verification.attempts >= MAX_VERIFICATION_ATTEMPTS:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Too many attempts. Please request a new code."}
        )
    
    # Increment attempts
    verification.attempts += 1
    db.commit()
    
    # Verify code - in mock mode, also accept "123456" directly as a fallback
    code_valid = verify_code(verify_data.code, verification.code_hash)
    if not code_valid and is_mock_mode() and verify_data.code == DEMO_VERIFICATION_CODE:
        code_valid = True
    
    if code_valid:
        # Mark as verified
        verification.verified_at = datetime.utcnow()
        user.phone_verified = True
        user.sms_verified_at = datetime.utcnow()
        db.commit()
        
        # Set SMS verified in session
        request.session["sms_verified"] = True
        
        return {
            "success": True,
            "message": "Phone verified successfully"
        }
    else:
        remaining = MAX_VERIFICATION_ATTEMPTS - verification.attempts
        return JSONResponse(
            status_code=400,
            content={
                "success": False, 
                "error": f"Invalid code. {remaining} attempts remaining."
            }
        )
