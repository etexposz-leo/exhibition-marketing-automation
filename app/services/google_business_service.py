import os
import httpx
from typing import Optional
from datetime import datetime


class GoogleBusinessService:
    """Service for Google Business Profile API integration."""
    
    BASE_URL = "https://businessdata.googleapis.com/v1"
    
    def __init__(self, api_key: Optional[str] = None, access_token: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_BUSINESS_API_KEY")
        self.access_token = access_token or os.getenv("GOOGLE_ACCESS_TOKEN")
        self.location_id = os.getenv("GOOGLE_BUSINESS_LOCATION_ID")
    
    def _get_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json"
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers
    
    async def create_local_post(self, content: str, location_id: Optional[str] = None) -> dict:
        """
        Create a local post on Google Business Profile.
        
        Args:
            content: The text content of the post
            location_id: Google Business Location ID
            
        Returns:
            dict with post ID and status
        """
        if not self.api_key and not self.access_token:
            return {
                "success": False,
                "error": "Google Business API not configured. Set GOOGLE_BUSINESS_API_KEY or GOOGLE_ACCESS_TOKEN environment variable.",
                "post_id": None
            }
        
        target_location_id = location_id or self.location_id
        if not target_location_id:
            return {
                "success": False,
                "error": "Google Business Location ID not configured. Set GOOGLE_BUSINESS_LOCATION_ID environment variable.",
                "post_id": None
            }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Build the API URL
                if self.access_token:
                    # Using OAuth2 access token
                    response = await client.post(
                        f"{self.BASE_URL}/{target_location_id}/localPosts",
                        headers=self._get_headers(),
                        json={
                            "languageCode": "en-US",
                            "summary": content,
                            "callToAction": {
                                "actionType": "LEARN_MORE"
                            }
                        }
                    )
                else:
                    # Using API key
                    response = await client.post(
                        f"{self.BASE_URL}/{target_location_id}/localPosts?key={self.api_key}",
                        headers=self._get_headers(),
                        json={
                            "languageCode": "en-US",
                            "summary": content,
                            "callToAction": {
                                "actionType": "LEARN_MORE"
                            }
                        }
                    )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    post_name = data.get("name", "")
                    return {
                        "success": True,
                        "post_id": post_name,
                        "url": f"https://business.google.com/posts/l/{target_location_id}",
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Google Business API error: {response.status_code} - {response.text}",
                        "post_id": None
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "post_id": None
            }
    
    async def get_locations(self) -> dict:
        """Get list of Google Business locations."""
        if not self.api_key and not self.access_token:
            return {"success": False, "error": "API not configured"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if self.access_token:
                    response = await client.get(
                        f"{self.BASE_URL}/accounts/-/locations",
                        headers=self._get_headers()
                    )
                else:
                    response = await client.get(
                        f"{self.BASE_URL}/accounts/-/locations?key={self.api_key}",
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
    
    async def list_posts(self, location_id: Optional[str] = None) -> dict:
        """List local posts for a location."""
        if not self.api_key and not self.access_token:
            return {"success": False, "error": "API not configured"}
        
        target_location_id = location_id or self.location_id
        if not target_location_id:
            return {"success": False, "error": "Location ID not provided"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if self.access_token:
                    response = await client.get(
                        f"{self.BASE_URL}/{target_location_id}/localPosts",
                        headers=self._get_headers()
                    )
                else:
                    response = await client.get(
                        f"{self.BASE_URL}/{target_location_id}/localPosts?key={self.api_key}",
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
        """Check if Google Business API is configured."""
        return bool(self.api_key or self.access_token) and bool(self.location_id)


# Singleton instance
def get_google_business_service(
    api_key: Optional[str] = None, 
    access_token: Optional[str] = None
) -> GoogleBusinessService:
    return GoogleBusinessService(api_key, access_token)
