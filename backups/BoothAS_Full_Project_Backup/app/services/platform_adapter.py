"""
Unified Social Platform Adapter Architecture

Base class and registry for all social media platform adapters.
Each platform implements the same interface for consistent publishing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum
import random
import string
from datetime import datetime


class PlatformType(Enum):
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    X_TWITTER = "x"
    GOOGLE_BUSINESS = "google_business"


@dataclass
class PublishResult:
    """Standardized result from any platform publish operation."""
    success: bool
    platform: str
    post_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    is_mock: bool = False
    published_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "platform": self.platform,
            "post_id": self.post_id,
            "url": self.url,
            "error": self.error,
            "is_mock": self.is_mock,
            "published_at": self.published_at,
            **({} if not self.metadata else self.metadata)
        }


@dataclass
class PlatformConfig:
    """Configuration for a social platform."""
    platform: PlatformType
    name: str
    icon: str
    color: str
    character_limit: int
    supports_images: bool
    requires_auth: bool = True


class BasePlatformAdapter(ABC):
    """
    Abstract base class for all social platform adapters.
    
    All platform implementations must follow this interface:
    - publish(): Publish content to the platform (async)
    - publish_sync(): Publish content to the platform (sync)
    - is_configured(): Check if API credentials are available
    - validate_content(): Validate content for platform requirements
    """
    
    config: PlatformConfig
    
    @abstractmethod
    async def publish(self, content: str, **kwargs) -> PublishResult:
        """
        Publish content to the platform (async).
        
        Args:
            content: The text content to publish
            **kwargs: Platform-specific options (image_url, etc.)
            
        Returns:
            PublishResult with success status and post details
        """
        pass
    
    def publish_sync(self, content: str, **kwargs) -> PublishResult:
        """
        Synchronous publish - for scheduler use.
        Default implementation wraps async publish.
        """
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new loop if we're in an async context
                result = loop.run_until_complete(self.publish(content, **kwargs))
            else:
                result = loop.run_until_complete(self.publish(content, **kwargs))
            return result
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.publish(content, **kwargs))
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the platform API is properly configured."""
        pass
    
    def validate_content(self, content: str) -> tuple[bool, Optional[str]]:
        """
        Validate content for platform requirements.
        
        Returns:
            (is_valid, error_message)
        """
        if not content or not content.strip():
            return False, "Content cannot be empty"
        
        if len(content) > self.config.character_limit:
            return False, f"Content exceeds {self.config.character_limit} character limit"
        
        return True, None
    
    def generate_mock_id(self) -> str:
        """Generate a mock post ID for testing."""
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"MOCK_{self.config.platform.value.upper()}_{suffix}"
    
    def _get_mock_url(self, post_id: str) -> str:
        """Generate a mock URL for the post."""
        urls = {
            PlatformType.LINKEDIN: f"https://www.linkedin.com/feed/update/{post_id}",
            PlatformType.FACEBOOK: f"https://www.facebook.com/{post_id}",
            PlatformType.INSTAGRAM: f"https://www.instagram.com/p/{post_id}",
            PlatformType.X_TWITTER: f"https://x.com/i/status/{post_id}",
            PlatformType.GOOGLE_BUSINESS: f"https://business.google.com/posts/l/MOCK",
        }
        return urls.get(self.config.platform, f"https://example.com/posts/{post_id}")


class MockPlatformAdapter(BasePlatformAdapter):
    """
    Mock adapter that simulates publishing without API credentials.
    Used when real API is not configured.
    """
    
    def __init__(self, platform_type: PlatformType):
        self.config = PlatformConfig(
            platform=platform_type,
            name=platform_type.value.replace("_", " ").title(),
            icon=self._get_icon(platform_type),
            color=self._get_color(platform_type),
            character_limit=self._get_limit(platform_type),
            supports_images=platform_type in [PlatformType.INSTAGRAM, PlatformType.FACEBOOK],
            requires_auth=False
        )
    
    def _get_icon(self, p: PlatformType) -> str:
        icons = {
            PlatformType.LINKEDIN: "📎",
            PlatformType.FACEBOOK: "📘",
            PlatformType.INSTAGRAM: "📸",
            PlatformType.X_TWITTER: "🐦",
            PlatformType.GOOGLE_BUSINESS: "📍",
        }
        return icons.get(p, "📱")
    
    def _get_color(self, p: PlatformType) -> str:
        colors = {
            PlatformType.LINKEDIN: "#0A66C2",
            PlatformType.FACEBOOK: "#1877F2",
            PlatformType.INSTAGRAM: "#E4405F",
            PlatformType.X_TWITTER: "#000000",
            PlatformType.GOOGLE_BUSINESS: "#EA4335",
        }
        return colors.get(p, "#666666")
    
    def _get_limit(self, p: PlatformType) -> int:
        limits = {
            PlatformType.LINKEDIN: 3000,
            PlatformType.FACEBOOK: 63206,
            PlatformType.INSTAGRAM: 2200,
            PlatformType.X_TWITTER: 280,
            PlatformType.GOOGLE_BUSINESS: 1500,
        }
        return limits.get(p, 1000)
    
    async def publish(self, content: str, **kwargs) -> PublishResult:
        """Simulate publishing to the platform (async version)."""
        return self._do_publish(content, **kwargs)
    
    def publish_sync(self, content: str, **kwargs) -> PublishResult:
        """Simulate publishing to the platform (sync version - same logic)."""
        return self._do_publish(content, **kwargs)
    
    def _do_publish(self, content: str, **kwargs) -> PublishResult:
        """Common publish logic for both sync and async."""
        is_valid, error = self.validate_content(content)
        if not is_valid:
            return PublishResult(
                success=False,
                platform=self.config.platform.value,
                error=error,
                is_mock=True
            )
        
        post_id = self.generate_mock_id()
        return PublishResult(
            success=True,
            platform=self.config.platform.value,
            post_id=post_id,
            url=self._get_mock_url(post_id),
            is_mock=True,
            published_at=datetime.utcnow().isoformat(),
            metadata={
                "content_preview": content[:100] + "..." if len(content) > 100 else content,
                "character_count": len(content),
                "character_limit": self.config.character_limit
            }
        )
    
    def is_configured(self) -> bool:
        """Mock is always "configured" since it doesn't need credentials."""
        return True


class PlatformRegistry:
    """
    Registry for all platform adapters.
    Provides unified access to all platforms.
    """
    
    _adapters: Dict[PlatformType, BasePlatformAdapter] = {}
    _mock_adapters: Dict[PlatformType, MockPlatformAdapter] = {}
    
    @classmethod
    def register(cls, platform: PlatformType, adapter: BasePlatformAdapter):
        """Register a platform adapter."""
        cls._adapters[platform] = adapter
    
    @classmethod
    def get_adapter(cls, platform: PlatformType, use_mock: bool = True) -> BasePlatformAdapter:
        """
        Get an adapter for a platform.
        
        Args:
            platform: The platform type
            use_mock: If True, use mock when real API is not configured
        """
        # If real adapter exists and is configured, use it
        if platform in cls._adapters:
            adapter = cls._adapters[platform]
            if adapter.is_configured():
                return adapter
        
        # Use mock adapter
        if platform not in cls._mock_adapters:
            cls._mock_adapters[platform] = MockPlatformAdapter(platform)
        return cls._mock_adapters[platform]
    
    @classmethod
    def get_all_platforms(cls) -> List[PlatformConfig]:
        """Get all available platform configurations."""
        configs = []
        for platform in PlatformType:
            adapter = cls.get_adapter(platform)
            configs.append(adapter.config)
        return configs
    
    @classmethod
    def get_configured_platforms(cls) -> List[PlatformConfig]:
        """Get only configured platform configurations."""
        return [a.config for p, a in cls._adapters.items() if a.is_configured()]
    
    @classmethod
    async def publish_to_all(
        cls, 
        platforms: List[PlatformType], 
        content: str, 
        **kwargs
    ) -> List[PublishResult]:
        """Publish content to multiple platforms."""
        results = []
        for platform in platforms:
            adapter = cls.get_adapter(platform)
            result = await adapter.publish(content, **kwargs)
            results.append(result)
        return results


# Initialize mock adapters
for platform in PlatformType:
    PlatformRegistry._mock_adapters[platform] = MockPlatformAdapter(platform)


def get_platform_adapter(platform: str, use_mock: bool = True) -> BasePlatformAdapter:
    """Convenience function to get a platform adapter by name."""
    try:
        platform_type = PlatformType(platform.lower())
        return PlatformRegistry.get_adapter(platform_type, use_mock)
    except ValueError:
        raise ValueError(f"Unknown platform: {platform}. Valid platforms: {[p.value for p in PlatformType]}")


def get_all_platform_configs() -> List[Dict[str, Any]]:
    """Get configuration for all platforms (for UI)."""
    configs = []
    for platform in PlatformType:
        adapter = PlatformRegistry.get_adapter(platform)
        config = adapter.config
        configs.append({
            "id": config.platform.value,
            "name": config.name,
            "icon": config.icon,
            "color": config.color,
            "character_limit": config.character_limit,
            "supports_images": config.supports_images,
            "is_configured": adapter.is_configured(),
            "is_mock": type(adapter) == MockPlatformAdapter
        })
    return configs