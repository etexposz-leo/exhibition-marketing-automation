"""Opt-in cloud review runtime. No schema mutation or automatic external execution."""
import os
from urllib.parse import urlsplit


def enabled():
    return os.getenv('MARKETING_CLOUD_MODE') == 'true'


def base_url():
    value = os.getenv('APP_BASE_URL', '').rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise RuntimeError('Cloud APP_BASE_URL must be an HTTPS origin')
    return value


def configure():
    if not enabled():
        return
    runtime_file = os.getenv('MARKETING_RUNTIME_FILE')
    if runtime_file:
        import json
        import stat
        from pathlib import Path
        path = Path(runtime_file)
        if not path.is_absolute() or path.is_symlink():
            raise RuntimeError('Invalid protected cloud runtime file')
        if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RuntimeError('Cloud runtime file must be private (0600)')
        values = json.loads(path.read_text(encoding='utf-8'))
        allowed = {'SECRET_KEY', 'CREDENTIAL_KEYS', 'CREDENTIAL_ACTIVE_KEY', 'DATABASE_URL', 'MARKETING_OWNER_ID'}
        if set(values) != allowed or not all(isinstance(v,str) for v in values.values()):
            raise RuntimeError('Invalid cloud runtime configuration')
        os.environ.update(values)
    origin = base_url()
    from app.services.publishing_catalog import CATALOG
    for platform in CATALOG:
        os.environ[platform.upper() + '_REAL_PUBLISH_ENABLED'] = 'false'
    for name in ('LEAD_REAL_EMAIL_SEND_ENABLED','ENABLE_SCHEDULER','EXPO_CRAWLER_WORKER_ENABLED',
                 'ENABLE_LINKEDIN_WORKER','ENABLE_DEMO_ACCOUNT','ENABLE_MOCK_PUBLISHING','SMS_MOCK_MODE'):
        os.environ[name] = 'false'
    os.environ.update(CHANNEL_WORKSPACE_ORIGIN=origin, MARKETING_LOCAL_AUTH='true', HTTPS_ONLY='true', EXECUTION_MODE='TEST')


def workspace_config():
    try:
        owner = int(os.environ['MARKETING_OWNER_ID'])
        if owner <= 0: raise ValueError()
    except (ValueError, KeyError):
        raise RuntimeError('A verified MARKETING_OWNER_ID is required') from None
    return dict(backlink_owner_id=owner, backlink_root=None, cloud_mode=True)


def validate_database(engine):
    """Reject incomplete deployment instead of auto-creating tables on a live DB."""
    from sqlalchemy import inspect, text
    from app.core.credentials import CredentialStore
    from app.models.models import Base
    CredentialStore()  # Only validate configured encryption; do not print or replace keys.
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in present:
            raise RuntimeError('Cloud database schema is not ready; explicit migration required')
        columns = {item['name'] for item in inspector.get_columns(table.name)}
        if not set(table.columns.keys()).issubset(columns):
            raise RuntimeError('Cloud database schema is not ready; explicit migration required')
    with engine.connect() as connection:
        row = connection.execute(text('SELECT is_active, is_demo FROM users WHERE id=:owner'),
            dict(owner=workspace_config()['backlink_owner_id'])).first()
        if not row or not row[0] or row[1]:
            raise RuntimeError('Cloud Owner must be an existing active non-demo account')
    from sqlalchemy.orm import Session
    from app.core.cloud_auth import SCOPE
    import json
    with Session(engine) as db:
        try:
            value = json.loads(CredentialStore().get(db, workspace_config()['backlink_owner_id'], SCOPE, 'record'))
            if not value.get('secret') or not isinstance(value.get('last_counter'),int):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('Cloud Owner MFA enrollment is required') from None
