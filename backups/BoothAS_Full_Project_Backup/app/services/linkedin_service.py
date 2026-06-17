import os
import httpx
from typing import Optional


class LinkedInService:
    """Service for LinkedIn API integration."""
    
    BASE_URL = "https://api.linkedin.com/v2"
    V2_URL = "https://api.linkedin.com/v2"
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("LINKEDIN_ACCESS_TOKEN")
        self.client_id = os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    
    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }
    
    async def post_text(self, content: str, profile_id: str = "me") -> dict:
        """
        Post a text update to LinkedIn.
        
        Args:
            content: The text content of the post
            profile_id: LinkedIn profile ID (default: "me" for authenticated user)
            
        Returns:
            dict with post ID and status
        """
        if not self.access_token:
            return {
                "success": False,
                "error": "LinkedIn access token not configured. Set LINKEDIN_ACCESS_TOKEN environment variable.",
                "post_id": None
            }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create the post
                post_data = {
                    "author": f"urn:li:person:{profile_id}" if profile_id != "me" else "urn:li:person:USER_ID",
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": content
                            },
                            "shareMediaCategory": "NONE"
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                    }
                }
                
                response = await client.post(
                    f"{self.BASE_URL}/ugcPosts",
                    headers=self._get_headers(),
                    json=post_data
                )
                
                if response.status_code == 201:
                    post_id = response.headers.get("x-restli-id", "")
                    return {
                        "success": True,
                        "post_id": post_id,
                        "url": f"https://www.linkedin.com/posts/{post_id}",
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "error": f"LinkedIn API error: {response.status_code} - {response.text}",
                        "post_id": None
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "post_id": None
            }
    
    async def get_profile(self, profile_id: str = "me") -> dict:
        """Get LinkedIn profile information."""
        if not self.access_token:
            return {"success": False, "error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/people/{profile_id}",
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
                        "error": response.text
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def is_configured(self) -> bool:
        """Check if LinkedIn API is configured."""
        return bool(self.access_token)


# Singleton instance
def get_linkedin_service(access_token: Optional[str] = None) -> LinkedInService:
    return LinkedInService(access_token)
