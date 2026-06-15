from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum as SQLEnum
from datetime import datetime
from app.core.database import Base
import enum


class SocialPlatform(enum.Enum):
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    GOOGLE_BUSINESS = "google_business"


class PostStatus(enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False)  # linkedin, facebook, google_business
    account_name = Column(String(200), nullable=False)
    account_id = Column(String(200), nullable=True)  # Platform-specific ID
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    is_mock_mode = Column(Boolean, default=False)  # Enable mock posting mode
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    customer_industry = Column(String(200), nullable=False)
    exhibition_name = Column(String(300), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GeneratedContent(Base):
    __tablename__ = "generated_contents"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, nullable=False)
    content_type = Column(String(50), nullable=False)  # linkedin, facebook, google_business, image_prompt
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, nullable=True)
    content_id = Column(Integer, nullable=True)
    platform = Column(String(50), nullable=False)  # linkedin, facebook, google_business
    social_account_id = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)  # Can be null for immediate posts
    published_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="scheduled")  # draft, scheduled, published, failed
    platform_post_id = Column(String(200), nullable=True)  # ID from the platform after publishing
    error_message = Column(Text, nullable=True)
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
