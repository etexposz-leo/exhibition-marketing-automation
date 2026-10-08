"""
Instagram Platform Adapter

Supports publishing to Instagram via Graph API.
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


class InstagramAdapter(BasePlatformAdapter):
    """
    Instagram Graph API adapter.
    
    Requires:
    - INSTAGRAM_ACCESS_TOKEN: Facebook Graph API access token with Instagram permissions
    - INSTAGRAM_ACCOUNT_ID: Instagram Business Account ID
    """
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
        self.config = PlatformConfig(
            platform=PlatformType.INSTAGRAM,
            name="Instagram",
            icon="📸",
            color="#E4405F",
            character_limit=2200,
            supports_images=True,
            requires_auth=True
        )
    
    def is_configured(self) -> bool:
        return bool(self.access_token and self.account_id)
    
    async def publish(self, content: str, **kwargs) -> PublishResult:
        """Publish a post to Instagram."""
        raise ValueError("External provider execution disabled in Phase 1")
        if not self.is_configured():
            raise ValueError("Adapter credentials unavailable")
        
        image_url = kwargs.get("image_url")
        
        if image_url:
            return await self._publish_photo(content, image_url)
        else:
            return await self._publish_container(content)
    
    async def _publish_container(self, caption: str) -> PublishResult:
        raise ValueError("External provider execution disabled in Phase 1")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/{self.account_id}/media",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    data={"caption": caption}
                )
                
                if response.status_code == 200:
                    container_id = response.json().get("id")
                    return await self._publish_container_final(container_id)
                else:
                    return PublishResult(
                        success=False,
                        platform=self.config.platform.value,
                        error="Provider request rejected"
                    )
        except Exception as e:
            return PublishResult(success=False, platform=self.config.platform.value, error="Provider operation failed")
    
    async def _publish_container_final(self, container_id: str) -> PublishResult:
        raise ValueError("External provider execution disabled in Phase 1")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/{self.account_id}/media_publish",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    data={"creation_id": container_id}
                )
                
                if response.status_code == 200:
                    post_id = response.json().get("id")
                    return PublishResult(
                        success=True, platform=self.config.platform.value, post_id=post_id,
                        url=f"https://www.instagram.com/p/{post_id}", published_at=self._timestamp()
                    )
                return PublishResult(success=False, platform=self.config.platform.value, error="Provider request rejected")
        except Exception as e:
            return PublishResult(success=False, platform=self.config.platform.value, error="Provider operation failed")
    
    async def _publish_photo(self, caption: str, image_url: str) -> PublishResult:
        raise ValueError("External provider execution disabled in Phase 1")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/{self.account_id}/media",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    data={"image_url": image_url, "caption": caption}
                )
                if response.status_code == 200:
                    container_id = response.json().get("id")
                    return await self._publish_container_final(container_id)
                return PublishResult(success=False, platform=self.config.platform.value, error="Provider request rejected")
        except Exception as e:
            return PublishResult(success=False, platform=self.config.platform.value, error="Provider operation failed")
    
    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat()