"""
Mock Publishers for Ad Draft Platform

⚠️ IMPORTANT: These are DRY-RUN only publishers.
They NEVER call real APIs and NEVER publish real ads.

This module provides mock implementations for:
- GoogleAdsMockPublisher
- LinkedInMockPublisher  
- FacebookMockPublisher
- GoogleBusinessMockPublisher
- EmailMockPublisher
- SEOMockPublisher

All publishers log their actions and NEVER spend money.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of a publish attempt."""
    success: bool
    mock_mode: bool = True  # Always True for these publishers
    platform_post_id: Optional[str] = None
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    cost_cents: int = 0  # Always 0
    impressions: int = 0  # Always 0
    clicks: int = 0  # Always 0
    response_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BaseMockPublisher(ABC):
    """
    Base class for all mock publishers.
    
    IMPORTANT: These publishers are DRY-RUN ONLY.
    They log everything but NEVER call real APIs.
    """
    
    platform_name: str = "unknown"
    
    # Keywords that indicate sensitive content
    SENSITIVE_KEYWORDS = [
        "free money", "guaranteed", "no questions asked",
        "click here now", "limited time offer",
        "act now", "don't miss", "winner", "prize"
    ]
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        Initialize mock publisher.
        
        Args:
            api_key: NOT USED - kept for API compatibility only
            **kwargs: Additional configuration (also not used in mock mode)
        """
        self._api_key = api_key  # Stored but never used
        self._enabled = False  # Mock publishers are disabled by default
        self._config = kwargs
        
        logger.warning(
            f"[{self.platform_name.upper()}] MOCK PUBLISHER INITIALIZED - "
            "This is DRY-RUN ONLY. No real ads will be published."
        )
    
    def is_enabled(self) -> bool:
        """Check if publisher is enabled (always False for mock)."""
        return self._enabled
    
    def enable(self):
        """Enable the publisher (still in mock/dry-run mode)."""
        self._enabled = True
        logger.info(f"[{self.platform_name.upper()}] Mock publisher ENABLED (dry-run mode)")
    
    def disable(self):
        """Disable the publisher."""
        self._enabled = False
        logger.info(f"[{self.platform_name.upper()}] Mock publisher DISABLED")
    
    @abstractmethod
    def validate_content(self, content: Dict) -> List[str]:
        """
        Validate ad content for policy compliance.
        
        Returns list of warnings (empty if no issues).
        """
        pass
    
    @abstractmethod
    async def publish(self, content: Dict) -> PublishResult:
        """
        Publish content (DRY-RUN ONLY).
        
        This method NEVER calls real APIs.
        It logs the action and returns a mock response.
        """
        pass
    
    async def dry_run(self, content: Dict) -> PublishResult:
        """
        Run a dry-run validation without publishing.
        
        This is the safest way to test before approval.
        """
        logger.info(f"[{self.platform_name.upper()}] DRY-RUN: Validating content...")
        
        warnings = self.validate_content(content)
        
        result = PublishResult(
            success=True,
            mock_mode=True,
            message=f"DRY-RUN SUCCESSFUL for {self.platform_name}. No real publish occurred.",
            warnings=warnings,
            response_data={
                "dry_run": True,
                "platform": self.platform_name,
                "validated_at": datetime.utcnow().isoformat(),
                "warnings": warnings,
                "note": "This was a DRY-RUN. No real API calls were made."
            }
        )
        
        logger.info(
            f"[{self.platform_name.upper()}] DRY-RUN COMPLETE: "
            f"{'No warnings' if not warnings else f'{len(warnings)} warnings'}"
        )
        
        return result
    
    def _log_publish_attempt(self, content: Dict, action: str = "publish"):
        """Log a publish attempt for audit trail."""
        logger.info(
            f"[{self.platform_name.upper()}] {action.upper()} ATTEMPT "
            f"(MOCK MODE): {content.get('title', 'No title')[:50]}..."
        )


class GoogleAdsMockPublisher(BaseMockPublisher):
    """
    Mock publisher for Google Ads.
    
    ⚠️ DRY-RUN ONLY - Never calls Google Ads API
    """
    
    platform_name = "google_ads"
    
    def validate_content(self, content: Dict) -> List[str]:
        """Validate Google Ads content."""
        warnings = []
        
        title = content.get("title", "")
        body = content.get("body", "")
        
        # Check character limits
        if len(title) > 30:
            warnings.append("Title exceeds 30 characters for responsive search ads")
        if len(body) > 90:
            warnings.append("Description exceeds 90 characters")
        
        # Check for sensitive content
        combined = (title + " " + body).lower()
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword in combined:
                warnings.append(f"Potentially sensitive keyword: '{keyword}'")
        
        # Check for URL
        if not content.get("landing_page"):
            warnings.append("No landing page URL specified")
        
        return warnings
    
    async def publish(self, content: Dict) -> PublishResult:
        """
        Publish to Google Ads (DRY-RUN ONLY).
        
        ⚠️ THIS NEVER CALLS THE GOOGLE ADS API
        """
        self._log_publish_attempt(content, "google_ads_publish")
        
        warnings = self.validate_content(content)
        
        # Generate mock post ID
        mock_post_id = f"gads_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.warning(
            f"[GOOGLE ADS] ⚠️ DRY-RUN MODE - No real ad was published!\n"
            f"  Title: {content.get('title', 'N/A')[:50]}\n"
            f"  Budget: ${content.get('suggested_budget', 0)} (NOT charged)\n"
            f"  Keywords: {content.get('target_keywords', [])[:3]}\n"
            f"  Post ID would be: {mock_post_id}"
        )
        
        return PublishResult(
            success=True,
            mock_mode=True,
            platform_post_id=mock_post_id,
            message="DRY-RUN: Google Ads would be published here (mock mode)",
            warnings=warnings,
            response_data={
                "mock": True,
                "platform": "google_ads",
                "post_id": mock_post_id,
                "budget_would_be": content.get("suggested_budget", 0),
                "note": "DRY-RUN ONLY - No real Google Ads API called"
            }
        )


class LinkedInMockPublisher(BaseMockPublisher):
    """
    Mock publisher for LinkedIn.
    
    ⚠️ DRY-RUN ONLY - Never calls LinkedIn Marketing API
    """
    
    platform_name = "linkedin"
    
    def validate_content(self, content: Dict) -> List[str]:
        """Validate LinkedIn content."""
        warnings = []
        
        body = content.get("body", "")
        
        # Check character limits for LinkedIn posts
        if len(body) > 3000:
            warnings.append("Post exceeds 3000 character limit")
        
        # Check for hashtags
        if "#" in body and body.count("#") > 5:
            warnings.append("Consider limiting hashtags to 3-5 for better engagement")
        
        # Check for URLs
        if body.count("http") > 3:
            warnings.append("Multiple URLs may reduce engagement")
        
        return warnings
    
    async def publish(self, content: Dict) -> PublishResult:
        """
        Publish to LinkedIn (DRY-RUN ONLY).
        
        ⚠️ THIS NEVER CALLS THE LINKEDIN API
        """
        self._log_publish_attempt(content, "linkedin_publish")
        
        warnings = self.validate_content(content)
        
        mock_post_id = f"li_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.warning(
            f"[LINKEDIN] ⚠️ DRY-RUN MODE - No real post was published!\n"
            f"  Content: {content.get('body', 'N/A')[:100]}...\n"
            f"  CTA: {content.get('cta', 'N/A')}\n"
            f"  Post ID would be: {mock_post_id}"
        )
        
        return PublishResult(
            success=True,
            mock_mode=True,
            platform_post_id=mock_post_id,
            message="DRY-RUN: LinkedIn post would be published here (mock mode)",
            warnings=warnings,
            response_data={
                "mock": True,
                "platform": "linkedin",
                "post_id": mock_post_id,
                "note": "DRY-RUN ONLY - No real LinkedIn API called"
            }
        )


class FacebookMockPublisher(BaseMockPublisher):
    """
    Mock publisher for Facebook/Meta.
    
    ⚠️ DRY-RUN ONLY - Never calls Meta Marketing API
    """
    
    platform_name = "facebook"
    
    def validate_content(self, content: Dict) -> List[str]:
        """Validate Facebook content."""
        warnings = []
        
        body = content.get("body", "")
        
        # Check character limits
        if len(body) > 63206:
            warnings.append("Post exceeds 63,206 character limit")
        
        # Check for excessive caps
        caps_ratio = sum(1 for c in body if c.isupper()) / max(len(body), 1)
        if caps_ratio > 0.5:
            warnings.append("Excessive capitalization may reduce reach")
        
        # Check for prohibited content indicators
        prohibited = ["buy now", "order now", "call now"]
        for phrase in prohibited:
            if phrase in body.lower():
                warnings.append(f"Consider making '{phrase}' softer for better engagement")
        
        return warnings
    
    async def publish(self, content: Dict) -> PublishResult:
        """
        Publish to Facebook (DRY-RUN ONLY).
        
        ⚠️ THIS NEVER CALLS THE META API
        """
        self._log_publish_attempt(content, "facebook_publish")
        
        warnings = self.validate_content(content)
        
        mock_post_id = f"fb_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.warning(
            f"[FACEBOOK] ⚠️ DRY-RUN MODE - No real post was published!\n"
            f"  Content: {content.get('body', 'N/A')[:100]}...\n"
            f"  Target: {content.get('target_audience', 'N/A')}\n"
            f"  Post ID would be: {mock_post_id}"
        )
        
        return PublishResult(
            success=True,
            mock_mode=True,
            platform_post_id=mock_post_id,
            message="DRY-RUN: Facebook post would be published here (mock mode)",
            warnings=warnings,
            response_data={
                "mock": True,
                "platform": "facebook",
                "post_id": mock_post_id,
                "note": "DRY-RUN ONLY - No real Meta API called"
            }
        )


class GoogleBusinessMockPublisher(BaseMockPublisher):
    """
    Mock publisher for Google Business Profile.
    
    ⚠️ DRY-RUN ONLY - Never calls Google Business API
    """
    
    platform_name = "google_business"
    
    def validate_content(self, content: Dict) -> List[str]:
        """Validate Google Business content."""
        warnings = []
        
        body = content.get("body", "")
        
        # Check character limits
        if len(body) > 1500:
            warnings.append("Post exceeds 1500 character limit for Google Business")
        
        # Check for call-to-action
        if not content.get("cta"):
            warnings.append("Consider adding a call-to-action button")
        
        return warnings
    
    async def publish(self, content: Dict) -> PublishResult:
        """
        Publish to Google Business (DRY-RUN ONLY).
        
        ⚠️ THIS NEVER CALLS THE GOOGLE BUSINESS API
        """
        self._log_publish_attempt(content, "google_business_publish")
        
        warnings = self.validate_content(content)
        
        mock_post_id = f"gmb_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.warning(
            f"[GOOGLE BUSINESS] ⚠️ DRY-RUN MODE - No real post was published!\n"
            f"  Content: {content.get('body', 'N/A')[:100]}...\n"
            f"  CTA: {content.get('cta', 'N/A')}\n"
            f"  Post ID would be: {mock_post_id}"
        )
        
        return PublishResult(
            success=True,
            mock_mode=True,
            platform_post_id=mock_post_id,
            message="DRY-RUN: Google Business post would be published here (mock mode)",
            warnings=warnings,
            response_data={
                "mock": True,
                "platform": "google_business",
                "post_id": mock_post_id,
                "note": "DRY-RUN ONLY - No real Google Business API called"
            }
        )


class EmailMockPublisher(BaseMockPublisher):
    """
    Mock publisher for Email campaigns.
    
    ⚠️ DRY-RUN ONLY - Never sends real emails
    """
    
    platform_name = "email"
    
    def validate_content(self, content: Dict) -> List[str]:
        """Validate email content."""
        warnings = []
        
        subject = content.get("email_subject", "")
        body = content.get("body", "")
        
        # Check subject length
        if len(subject) > 60:
            warnings.append("Subject line exceeds 60 characters")
        
        # Check for spam triggers
        spam_words = ["free", "discount", "offer", "buy", "sale"]
        for word in spam_words:
            if word in subject.lower():
                warnings.append(f"Subject may trigger spam filters: '{word}'")
        
        # Check for unsubscribe
        if "unsubscribe" not in body.lower():
            warnings.append("Include unsubscribe link for compliance")
        
        return warnings
    
    async def publish(self, content: Dict) -> PublishResult:
        """
        Send email (DRY-RUN ONLY).
        
        ⚠️ THIS NEVER CALLS ANY EMAIL API
        """
        self._log_publish_attempt(content, "email_send")
        
        warnings = self.validate_content(content)
        
        mock_post_id = f"email_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        recipients = content.get("email_recipients", [])
        
        logger.warning(
            f"[EMAIL] ⚠️ DRY-RUN MODE - No real emails were sent!\n"
            f"  Subject: {content.get('email_subject', 'N/A')}\n"
            f"  Recipients: {len(recipients) if isinstance(recipients, list) else 'N/A'}\n"
            f"  Campaign ID would be: {mock_post_id}"
        )
        
        return PublishResult(
            success=True,
            mock_mode=True,
            platform_post_id=mock_post_id,
            message=f"DRY-RUN: Email would be sent to {len(recipients) if isinstance(recipients, list) else 'N/A'} recipients (mock mode)",
            warnings=warnings,
            response_data={
                "mock": True,
                "platform": "email",
                "campaign_id": mock_post_id,
                "recipient_count": len(recipients) if isinstance(recipients, list) else 0,
                "note": "DRY-RUN ONLY - No real emails sent"
            }
        )


class SEOMockPublisher(BaseMockPublisher):
    """
    Mock publisher for SEO articles.
    
    ⚠️ DRY-RUN ONLY - Never publishes to CMS
    """
    
    platform_name = "seo_article"
    
    def validate_content(self, content: Dict) -> List[str]:
        """Validate SEO content."""
        warnings = []
        
        title = content.get("title", "")
        body = content.get("body", "")
        meta_desc = content.get("seo_meta_description", "")
        
        # Check title length
        if len(title) > 60:
            warnings.append("Title exceeds 60 characters for SEO best practice")
        if len(title) < 30:
            warnings.append("Title is too short for SEO")
        
        # Check meta description
        if len(meta_desc) > 160:
            warnings.append("Meta description exceeds 160 characters")
        
        # Check content length
        word_count = len(body.split())
        if word_count < 300:
            warnings.append("Content is too short (aim for 300+ words)")
        
        # Check for keywords
        keywords = content.get("seo_keywords", [])
        if not keywords:
            warnings.append("No SEO keywords specified")
        
        return warnings
    
    async def publish(self, content: Dict) -> PublishResult:
        """
        Publish SEO article (DRY-RUN ONLY).
        
        ⚠️ THIS NEVER PUBLISHES TO ANY CMS
        """
        self._log_publish_attempt(content, "seo_publish")
        
        warnings = self.validate_content(content)
        
        mock_post_id = f"seo_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        logger.warning(
            f"[SEO ARTICLE] ⚠️ DRY-RUN MODE - No real article was published!\n"
            f"  Title: {content.get('title', 'N/A')[:50]}\n"
            f"  Keywords: {content.get('seo_keywords', [])[:3]}\n"
            f"  Article ID would be: {mock_post_id}"
        )
        
        return PublishResult(
            success=True,
            mock_mode=True,
            platform_post_id=mock_post_id,
            message="DRY-RUN: SEO article would be published here (mock mode)",
            warnings=warnings,
            response_data={
                "mock": True,
                "platform": "seo_article",
                "article_id": mock_post_id,
                "word_count": len(content.get("body", "").split()),
                "note": "DRY-RUN ONLY - No real CMS publish occurred"
            }
        )


# Factory function to get mock publisher by platform
def get_mock_publisher(platform: str) -> BaseMockPublisher:
    """
    Get the appropriate mock publisher for a platform.
    
    Args:
        platform: One of 'google_ads', 'linkedin', 'facebook', 
                  'google_business', 'email', 'seo_article'
    
    Returns:
        Mock publisher instance (always in DRY-RUN mode)
    """
    publishers = {
        "google_ads": GoogleAdsMockPublisher,
        "linkedin": LinkedInMockPublisher,
        "facebook": FacebookMockPublisher,
        "google_business": GoogleBusinessMockPublisher,
        "email": EmailMockPublisher,
        "seo_article": SEOMockPublisher,
    }
    
    publisher_class = publishers.get(platform.lower())
    if not publisher_class:
        raise ValueError(f"Unknown platform: {platform}")
    
    return publisher_class()


# List all available mock publishers
def list_mock_publishers() -> List[Dict[str, str]]:
    """List all available mock publishers with their status."""
    return [
        {
            "platform": "google_ads",
            "name": "Google Ads",
            "status": "mock_disabled",
            "description": "Responsive Search Ads, Display Ads"
        },
        {
            "platform": "linkedin",
            "name": "LinkedIn",
            "status": "mock_disabled", 
            "description": "Sponsored Posts, Company Updates"
        },
        {
            "platform": "facebook",
            "name": "Facebook/Meta",
            "status": "mock_disabled",
            "description": "Posts, Stories, Ads"
        },
        {
            "platform": "google_business",
            "name": "Google Business",
            "status": "mock_disabled",
            "description": "Business Profile Posts"
        },
        {
            "platform": "email",
            "name": "Email",
            "status": "mock_disabled",
            "description": "Newsletter Campaigns"
        },
        {
            "platform": "seo_article",
            "name": "SEO Article",
            "status": "mock_disabled",
            "description": "Blog Posts, Landing Pages"
        },
    ]


# IMPORTANT: Document the safety status
SAFETY_STATUS = {
    "all_publishers_mock": True,
    "real_api_enabled": False,
    "dry_run_mode": True,
    "auto_publish_enabled": False,
    "human_approval_required": True,
    "cost_tracking": "disabled",
    "note": "⚠️ ALL PUBLISHERS ARE IN DRY-RUN MODE. NO REAL ADS WILL BE PUBLISHED."
}
