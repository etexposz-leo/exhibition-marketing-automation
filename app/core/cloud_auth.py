"""Cloud password + TOTP authentication; independent from local/SMS acceptance."""
import base64
import json
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from cryptography.hazmat.primitives.twofactor import InvalidToken
from fastapi import HTTPException
from sqlalchemy import text
from app.core.credentials import CredentialStore
from app.core import local_login_guard, module_access
from app.core.auth import authenticate_user
from app.core.security import utcnow

SCOPE = 'cloud-owner-mfa-v1'


def valid_counter(secret, code, last_counter=-1, now=None):
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    now = time.time() if now is None else now
    otp = TOTP(base64.b32decode(secret), 6, hashes.SHA1(), 30)
    for counter in (int(now // 30), int(now // 30)-1, int(now // 30)+1):
        if counter <= last_counter:
            continue
        try:
            otp.verify(code.encode(), counter * 30)
            return counter
        except InvalidToken:
            continue
    return None


def login(db, request, email, password, code):
    attempt = local_login_guard.check(request, email)
    if len(password.encode()) > 72 or len(email) > 254:
        raise HTTPException(401, 'Invalid sign-in credentials')
    if db.bind.dialect.name != 'sqlite':
        raise HTTPException(503, 'Cloud MFA requires the validated SQLite backend')
    db.execute(text('BEGIN IMMEDIATE'))
    user = authenticate_user(db, email.strip().casefold(), password)
    if not user or user.is_demo:
        raise HTTPException(401, 'Invalid sign-in credentials')
    access = module_access.profile(db, user.id)
    if access['locked']:
        raise HTTPException(401, 'Invalid sign-in credentials')
    vault = CredentialStore()
    try:
        value = json.loads(vault.get(db, user.id, SCOPE, 'record'))
        counter = valid_counter(value['secret'], code, value['last_counter'])
    except (ValueError, KeyError, TypeError):
        counter = None
    if counter is None:
        raise HTTPException(401, 'Invalid sign-in credentials')
    value['last_counter'] = counter
    vault.put(db, user.id, SCOPE, 'record', json.dumps(value))
    db.commit()
    request.session.clear()
    request.session.update(user_id=user.id, user_email=user.email, username=user.username,
                           mfa_verified=True, module_session_version=access['session_version'])
    local_login_guard.success(attempt)
    return dict(success=True, requires_verification=False, redirect='/marketing', mfa='totp')
