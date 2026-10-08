"""Local login throttling; no password, email, or payload logging."""
import hashlib,threading,time
from fastapi import HTTPException
LOCK=threading.Lock();ATTEMPTS={}
def check(request,email):
    from app.core.cloud_runtime import enabled, base_url
    expected=base_url() if enabled() else 'https://localhost:18421'
    if request.headers.get('origin')!=expected:raise HTTPException(403,'Same-origin login required')
    now=time.monotonic();key=hashlib.sha256(email.strip().casefold().encode()).hexdigest()
    with LOCK:
        for k in list(ATTEMPTS):
            ATTEMPTS[k]=[t for t in ATTEMPTS[k] if now-t<900]
            if not ATTEMPTS[k]:del ATTEMPTS[k]
        # IP-wide limit prevents spraying account names on the loopback service.
        ip='ip:'+str(request.client.host if request.client else 'unknown')
        if len(ATTEMPTS.get(key,[]))>=5 or len(ATTEMPTS.get(ip,[]))>=30:raise HTTPException(429,'Too many sign-in attempts; wait 15 minutes')
        ATTEMPTS.setdefault(key,[]).append(now);ATTEMPTS.setdefault(ip,[]).append(now)
    return key
def success(key):
    with LOCK:ATTEMPTS.pop(key,None)
