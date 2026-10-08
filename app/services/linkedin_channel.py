"""LinkedIn member text publishing. All external access is opt-in and off by default."""
import os
import re
from datetime import timedelta
from urllib.parse import urlsplit
import httpx
from app.core.credentials import CredentialStore
from app.core.security import utcnow
from app.services.platform_adapter import BasePlatformAdapter, PlatformType, PlatformConfig, PublishResult

SCOPES = {'openid', 'profile', 'w_member_social'}


class OAuthConfigurationError(ValueError):
    """Safe, fixed diagnostics; never include configured values."""
    def __init__(self, code, message, fields):
        super().__init__(message)
        self.detail = dict(code=code, message=message, fields=fields)


def oauth_config():
    cfg = {k: os.getenv('LINKEDIN_' + k, '') for k in ('CLIENT_ID', 'CLIENT_SECRET', 'REDIRECT_URI', 'API_VERSION')}
    missing = ['LINKEDIN_' + k for k, value in cfg.items() if not value.strip()]
    if os.getenv('LINKEDIN_OAUTH_ENABLED') != 'true':
        missing.insert(0, 'LINKEDIN_OAUTH_ENABLED')
    if missing:
        raise OAuthConfigurationError('LINKEDIN_OAUTH_NOT_CONFIGURED',
            'LinkedIn OAuth is unavailable. Configure the listed server variables; set LINKEDIN_OAUTH_ENABLED=true.', missing)
    try:
        uri = urlsplit(cfg['REDIRECT_URI'])
        valid = uri.scheme == 'https' and uri.hostname and not uri.username and not uri.password and not uri.query and not uri.fragment and uri.path == '/api/linkedin/oauth/callback'
        uri.port
    except ValueError:
        valid = False
    if not valid:
        raise OAuthConfigurationError('LINKEDIN_REDIRECT_INVALID',
            'LinkedIn redirect URI must be an HTTPS URL ending in /api/linkedin/oauth/callback.', ['LINKEDIN_REDIRECT_URI'])
    if os.getenv('MARKETING_CLOUD_MODE') == 'true':
        from app.core.cloud_runtime import base_url
        try:
            expected = base_url() + '/api/linkedin/oauth/callback'
        except RuntimeError:
            raise OAuthConfigurationError('LINKEDIN_PUBLIC_ORIGIN_INVALID',
                'Configure the public HTTPS application origin.', ['APP_BASE_URL']) from None
        if cfg['REDIRECT_URI'] != expected or uri.hostname in ('localhost','127.0.0.1','::1'):
            raise OAuthConfigurationError('LINKEDIN_REDIRECT_ORIGIN_MISMATCH',
                'Cloud LinkedIn callback must match APP_BASE_URL and cannot use localhost.', ['LINKEDIN_REDIRECT_URI','APP_BASE_URL'])
    if not re.fullmatch(r'20\d{4}', cfg['API_VERSION']):
        raise OAuthConfigurationError('LINKEDIN_API_VERSION_INVALID',
            'Configure a supported LinkedIn API version in YYYYMM format.', ['LINKEDIN_API_VERSION'])
    return cfg


def real_enabled():
    return os.getenv('LINKEDIN_REAL_PUBLISH_ENABLED') == 'true'


def token_lifecycle(account, *, has_access=True, now=None):
    """Derived UTC lifecycle; no refresh token is assumed or fabricated."""
    now = now or utcnow()
    if not account.is_active or account.connection_status == 'disconnected':
        return 'DISCONNECTED'
    if (not has_access or account.connection_status != 'connected'
            or not account.token_expires_at or account.token_expires_at <= now + timedelta(seconds=60)):
        return 'REAUTH_REQUIRED'
    if account.token_expires_at <= now + timedelta(days=7):
        return 'TOKEN_EXPIRING'
    return 'CONNECTED'


class LinkedInHTTP:
    async def request(self, method, url, **kwargs):
        # Endpoints are fixed by code; no caller-supplied hosts or automatic retries.
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
            return await client.request(method, url, **kwargs)


http = LinkedInHTTP()


def validate_account(account):
    if not account or account.platform != 'linkedin' or not account.is_active:
        raise ValueError('LinkedIn account required')
    if account.account_type != 'member' or not re.fullmatch(r'urn:li:person:[A-Za-z0-9_-]+', account.account_id or ''):
        raise ValueError('Validated member identity required')
    if account.connection_status != 'connected' or not account.last_verified_at:
        raise ValueError('LinkedIn account must be verified')
    if not SCOPES.issubset(set((account.scopes or '').split())):
        raise ValueError('Required LinkedIn scopes missing')
    if not account.token_expires_at or account.token_expires_at <= utcnow() + timedelta(seconds=60):
        raise ValueError('LinkedIn reauthorization or refresh required')


class LinkedInAdapter(BasePlatformAdapter):
    config = PlatformConfig(PlatformType.LINKEDIN, 'LinkedIn', 'in', '#0A66C2', 3000, False)

    def is_configured(self):
        # No credentials are read here. The account-scoped vault is checked at execution.
        return real_enabled() and bool(os.getenv('LINKEDIN_API_VERSION'))

    async def publish(self, content, *, db=None, account=None, **kwargs):
        if not real_enabled():
            raise ValueError('Owner authorization required before real publishing')
        validate_account(account)
        valid, _ = self.validate_content(content)
        if not valid or db is None or db.info.get('owner_id') != account.user_id:
            raise ValueError('Invalid publish context')
        version = os.getenv('LINKEDIN_API_VERSION', '')
        if not re.fullmatch(r'20\d{4}', version):
            raise ValueError('LinkedIn API version required')
        token = CredentialStore().get(db, account.user_id, f'account:{account.id}', 'access_token')
        headers = {'Authorization': 'Bearer ' + token, 'LinkedIn-Version': version,
                   'X-Restli-Protocol-Version': '2.0.0', 'Content-Type': 'application/json'}
        payload = {'author': account.account_id, 'commentary': content, 'visibility': 'PUBLIC',
                   'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
                   'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False}
        try:
            response = await http.request('POST', 'https://api.linkedin.com/rest/posts', headers=headers, json=payload)
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.PoolTimeout):
            return failure('connection_not_established', retryable=True)
        except Exception:
            # Write/read timeouts may happen after LinkedIn accepted the post.
            return failure('delivery_uncertain', uncertain=True)
        if response.status_code == 201:
            ident = response.headers.get('x-restli-id', '')
            if not re.fullmatch(r'urn:li:(?:share|ugcPost):\d+', ident):
                return failure('confirmation_missing_identifier', uncertain=True)
            return PublishResult(True, 'linkedin', post_id=ident,
                url='https://www.linkedin.com/feed/update/' + ident + '/',
                published_at=utcnow().isoformat(), execution_mode='REAL', metadata={'confirmed': True})
        if response.status_code == 429:
            delay = response.headers.get('retry-after', '')
            seconds = min(max(int(delay), 60), 86400) if delay.isdigit() else 300
            return failure('rate_limited', retryable=True, retry_after=seconds)
        if response.status_code == 401:
            account.connection_status = 'reauth_required'
        if response.status_code >= 500 or response.status_code in {408, 409}:
            return failure('provider_result_uncertain', uncertain=True)
        return failure('provider_rejected_' + str(response.status_code))


def failure(code, retryable=False, uncertain=False, retry_after=0):
    return PublishResult(False, 'linkedin', error=code, execution_mode='REAL',
                         metadata={'retryable': retryable, 'uncertain': uncertain, 'retry_after': retry_after})
