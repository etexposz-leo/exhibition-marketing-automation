from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum as SQLEnum
from datetime import datetime
from app.core.database import Base
import enum


class SocialPlatform(enum.Enum):
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    X_TWITTER = "x"
    GOOGLE_BUSINESS = "google_business"


class PostStatus(enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class CampaignStatus(enum.Enum):
    CREATED = "created"
    CONTENT_GENERATED = "content_generated"
    OPTIMIZED = "optimized"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False)  # linkedin, facebook, instagram, x, google_business
    account_name = Column(String(200), nullable=False)
    account_id = Column(String(200), nullable=True)  # Platform-specific ID
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    api_key = Column(Text, nullable=True)  # Alternative API key storage
    token_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    is_mock_mode = Column(Boolean, default=True)  # Default to mock mode
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    customer_industry = Column(String(200), nullable=False)
    exhibition_name = Column(String(300), nullable=False)
    campaign_name = Column(String(300), nullable=True)  # Optional campaign name
    selected_platforms = Column(Text, nullable=True)  # JSON array of platform names
    status = Column(String(50), default="created")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GeneratedContent(Base):
    __tablename__ = "generated_contents"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, nullable=False)
    content_type = Column(String(50), nullable=False)  # linkedin, facebook, instagram, x, google_business, image_prompt
    content = Column(Text, nullable=False)
    is_optimized = Column(Boolean, default=False)  # Whether content has been optimized
    optimization_changes = Column(Text, nullable=True)  # JSON of changes made
    created_at = Column(DateTime, default=datetime.utcnow)


class OptimizedContent(Base):
    """Platform-specific optimized content for a campaign."""
    __tablename__ = "optimized_contents"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, nullable=False)
    content_id = Column(Integer, nullable=True)  # Reference to original GeneratedContent
    platform = Column(String(50), nullable=False)
    original_content = Column(Text, nullable=False)
    optimized_content = Column(Text, nullable=False)
    changes = Column(Text, nullable=True)  # JSON array of changes
    warnings = Column(Text, nullable=True)  # JSON array of warnings
    character_count = Column(Integer, default=0)
    character_limit = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, nullable=True)
    optimized_content_id = Column(Integer, nullable=True)  # Reference to OptimizedContent
    platform = Column(String(50), nullable=False)  # linkedin, facebook, instagram, x, google_business
    social_account_id = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)  # Can be null for immediate posts
    published_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="draft")  # draft, scheduled, published, failed
    platform_post_id = Column(String(200), nullable=True)  # ID from the platform after publishing
    url = Column(String(500), nullable=True)  # URL of the published post
    error_message = Column(Text, nullable=True)
    is_mock = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentTemplate(Base):
    """Content templates for different marketing styles."""
    __tablename__ = "content_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # Template name
    template_type = Column(String(50), nullable=False)  # professional, casual, promotional
    platform = Column(String(50), nullable=False)  # linkedin, facebook, google_business
    prompt_template = Column(Text, nullable=False)  # Template prompt for content generation
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
