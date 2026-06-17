import random
import string
from datetime import datetime
from typing import Optional


class MockPostingService:
    """Mock posting service for simulating social media posts without API credentials."""
    
    MOCK_USERNAMES = {
        "linkedin": "CompanyPage",
        "facebook": "CompanyPage",
        "google_business": "Business Profile"
    }
    
    def __init__(self, platform: str, account_name: Optional[str] = None):
        self.platform = platform
        self.account_name = account_name or self.MOCK_USERNAMES.get(platform, "Mock Account")
    
    def _generate_mock_id(self) -> str:
        """Generate a random mock post ID."""
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"MOCK_{self.platform.upper()}_{suffix}"
    
    def _generate_mock_url(self, post_id: str) -> str:
        """Generate a mock URL for the post."""
        if self.platform == "linkedin":
            return f"https://www.linkedin.com/feed/update/{post_id}"
        elif self.platform == "facebook":
            return f"https://www.facebook.com/{post_id}"
        elif self.platform == "google_business":
            return f"https://business.google.com/posts/l/MOCK_LOCATION"
        return f"https://example.com/posts/{post_id}"
    
    def post_text(self, content: str) -> dict:
        """
        Simulate posting text content to a social media platform.
        
        Returns a successful mock response with a generated post ID and URL.
        """
        post_id = self._generate_mock_id()
        url = self._generate_mock_url(post_id)
        
        return {
            "success": True,
            "post_id": post_id,
            "url": url,
            "platform": self.platform,
            "account": self.account_name,
            "content_preview": content[:100] + "..." if len(content) > 100 else content,
            "published_at": datetime.utcnow().isoformat(),
            "is_mock": True,
            "message": f"✅ Mock post published successfully to {self.platform}!"
        }
    
    def get_post_preview(self, content: str) -> dict:
        """Get a preview of how the post would look."""
        return {
            "platform": self.platform,
            "account": self.account_name,
            "content": content,
            "content_length": len(content),
            "character_limit_warning": self._check_character_limit(content),
            "preview": self._format_preview(content)
        }
    
    def _check_character_limit(self, content: str) -> Optional[str]:
        """Check if content exceeds platform character limits."""
        limits = {
            "linkedin": 3000,
            "facebook": 63206,
            "google_business": 1500
        }
        limit = limits.get(self.platform, 1000)
        
        if len(content) > limit:
            return f"Content exceeds {limit} character limit by {len(content) - limit} characters"
        return None
    
    def _format_preview(self, content: str) -> str:
        """Format a preview of the post."""
        preview_lines = [
            f"📱 Platform: {self.platform.upper()}",
            f"👤 Account: {self.account_name}",
            f"",
            f"📝 Content:",
            "-" * 40,
            content,
            "-" * 40,
        ]
        return "\n".join(preview_lines)


def get_mock_service(platform: str, account_name: Optional[str] = None) -> MockPostingService:
    """Get a mock posting service instance."""
    return MockPostingService(platform, account_name)