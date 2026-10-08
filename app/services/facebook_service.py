import os
import httpx
from typing import Optional


class FacebookService:
    """Service for Facebook Graph API integration."""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("FACEBOOK_ACCESS_TOKEN")
        self.page_id = os.getenv("FACEBOOK_PAGE_ID")
    
    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
    
    def _get_params(self) -> dict:
        return {}
    
    async def post_to_page(self, content: str, page_id: Optional[str] = None) -> dict:
        """
        Post a text update to a Facebook Page.
        
        Args:
            content: The text content of the post
            page_id: Facebook Page ID (defaults to FACEBOOK_PAGE_ID env var)
            
        Returns:
            dict with post ID and status
        """
        raise ValueError("External provider execution disabled in Phase 1")
        if not self.access_token:
            return {
                "success": False,
                "error": "Facebook access token not configured. Set FACEBOOK_ACCESS_TOKEN environment variable.",
                "post_id": None
            }
        
        target_page_id = page_id or self.page_id
        if not target_page_id:
            return {
                "success": False,
                "error": "Facebook Page ID not configured. Set FACEBOOK_PAGE_ID environment variable.",
                "post_id": None
            }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/{target_page_id}/feed",
                    headers=self._get_headers(),
                    json={
                        "message": content,
                        "published": "true"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    post_id = data.get("id", "")
                    return {
                        "success": True,
                        "post_id": post_id,
                        "url": f"https://www.facebook.com/{target_page_id}/posts/{post_id}",
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "error": "Provider request rejected",
                        "post_id": None
                    }
        except Exception as e:
            return {
                "success": False,
                "error": "Provider operation failed",
                "post_id": None
            }
    
    async def post_link(self, content: str, link_url: str, page_id: Optional[str] = None) -> dict:
        """
        Post a link with message to a Facebook Page.
        
        Args:
            content: The text content/caption of the post
            link_url: URL to link in the post
            page_id: Facebook Page ID
            
        Returns:
            dict with post ID and status
        """
        raise ValueError("External provider execution disabled in Phase 1")
        if not self.access_token:
            return {
                "success": False,
                "error": "Facebook access token not configured.",
                "post_id": None
            }
        
        target_page_id = page_id or self.page_id
        if not target_page_id:
            return {
                "success": False,
                "error": "Facebook Page ID not configured.",
                "post_id": None
            }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/{target_page_id}/feed",
                    headers=self._get_headers(),
                    json={
                        "message": content,
                        "link": link_url,
                        "published": "true"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    post_id = data.get("id", "")
                    return {
                        "success": True,
                        "post_id": post_id,
                        "url": f"https://www.facebook.com/{target_page_id}/posts/{post_id}",
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "error": "Provider request rejected",
                        "post_id": None
                    }
        except Exception as e:
            return {
                "success": False,
                "error": "Provider operation failed",
                "post_id": None
            }
    
    async def get_page_info(self, page_id: Optional[str] = None) -> dict:
        """Get Facebook Page information."""
        raise ValueError("External provider execution disabled in Phase 1")
        if not self.access_token:
            return {"success": False, "error": "Not authenticated"}
        
        target_page_id = page_id or self.page_id
        if not target_page_id:
            return {"success": False, "error": "Page ID not provided"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/{target_page_id}",
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": "Provider request rejected"
                    }
        except Exception as e:
            return {"success": False, "error": "Provider operation failed"}
    
    def is_configured(self) -> bool:
        """Check if Facebook API is configured."""
        return bool(self.access_token and self.page_id)


# Singleton instance
def get_facebook_service(access_token: Optional[str] = None) -> FacebookService:
    return FacebookService(access_token)
