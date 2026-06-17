"""
X (Twitter) Platform Adapter

Supports publishing to X via Twitter API v2.
"""

import os
import httpx
from typing import Optional

from app.services.platform_adapter import (
    BasePlatformAdapter,
    PlatformType,
    PlatformConfig,
    PublishResult
)


class XTwitterAdapter(BasePlatformAdapter):
    """
    X (Twitter) API v2 adapter.
    
    Requires:
    - X_BEARER_TOKEN: Twitter API v2 Bearer Token
    - X_API_KEY: Twitter API Key
    - X_API_SECRET: Twitter API Secret
    - X_ACCESS_TOKEN: User Access Token
    - X_ACCESS_TOKEN_SECRET: User Access Token Secret
    """
    
    BASE_URL = "https://api.twitter.com/2"
    
    def __init__(self):
        self.bearer_token = os.getenv("X_BEARER_TOKEN")
        self.api_key = os.getenv("X_API_KEY")
        self.api_secret = os.getenv("X_API_SECRET")
        self.access_token = os.getenv("X_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
        self.config = PlatformConfig(
            platform=PlatformType.X_TWITTER,
            name="X (Twitter)",
            icon="🐦",
            color="#000000",
            character_limit=280,
            supports_images=False,
            requires_auth=True
        )
    
    def is_configured(self) -> bool:
        # Need bearer token or all OAuth credentials
        return bool(self.bearer_token) or (bool(self.api_key) and bool(self.access_token))
    
    async def publish(self, content: str, **kwargs) -> PublishResult:
        """Publish a tweet to X."""
        if not self.is_configured():
            from app.services.platform_adapter import MockPlatformAdapter
            mock = MockPlatformAdapter(PlatformType.X_TWITTER)
            return await mock.publish(content, **kwargs)
        
        # Validate character limit for X
        if len(content) > 280:
            return PublishResult(
                success=False,
                platform=self.config.platform.value,
                error="X posts cannot exceed 280 characters"
            )
        
        return await self._post_tweet(content)
    
    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers
    
    async def _post_tweet(self, text: str) -> PublishResult:
        """Post a tweet using Twitter API v2."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Using OAuth2 with Bearer Token (App-only)
                response = await client.post(
                    f"{self.BASE_URL}/tweets",
                    headers=self._get_headers(),
                    json={"text": text}
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    tweet_id = data.get("data", {}).get("id")
                    return PublishResult(
                        success=True,
                        platform=self.config.platform.value,
                        post_id=tweet_id,
                        url=f"https://x.com/i/status/{tweet_id}",
                        published_at=self._timestamp()
                    )
                else:
                    return PublishResult(
                        success=False,
                        platform=self.config.platform.value,
                        error=f"X API error: {response.status_code} - {response.text}"
                    )
        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.config.platform.value,
                error=str(e)
            )
    
    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat()