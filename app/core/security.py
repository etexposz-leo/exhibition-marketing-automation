"""Phase 1 safety defaults. No external execution switch is provided."""
import os
import secrets
from datetime import datetime, timezone


def development_feature(name):
    return os.getenv('ENVIRONMENT') in {'development', 'test'} and os.getenv(name) == 'true'


def session_options():
    production = os.getenv('ENVIRONMENT') not in {'development', 'test'}
    key = os.getenv('SECRET_KEY')
    if production and (not key or len(key) < 32 or key.startswith('dev-secret')):
        raise RuntimeError('A strong SECRET_KEY is required in production')
    if production and (os.getenv('SMS_MOCK_MODE') == 'true' or os.getenv('ENABLE_DEMO_ACCOUNT') == 'true' or os.getenv('ENABLE_MOCK_PUBLISHING') == 'true'):
        raise RuntimeError('Development authentication features forbidden in production')
    return dict(secret_key=key or secrets.token_urlsafe(48), max_age=86400,
                same_site='lax', https_only=production or os.getenv('HTTPS_ONLY', 'true') == 'true')


def utcnow():
    # SQLite stores UTC without tzinfo; normalize all inputs at the boundary.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value is None or value.tzinfo is None:
        raise ValueError('scheduled_at must include a timezone')
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def safe_error(exc):
    # Do not serialize exception text, provider responses or request URLs.
    return 'Operation failed; sensitive diagnostic details withheld'
