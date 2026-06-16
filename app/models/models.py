from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum as SQLEnum, Float, Date
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


class User(Base):
    """User account for authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    company_name = Column(String(200), nullable=True)  # Company name
    is_active = Column(Boolean, default=True)
    is_demo = Column(Boolean, default=False)  # Demo account flag
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # User who owns this account
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
    user_id = Column(Integer, nullable=False, index=True)  # User who owns this campaign
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
    user_id = Column(Integer, nullable=False, index=True)  # User who owns this content
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
    user_id = Column(Integer, nullable=False, index=True)  # User who owns this content
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
    user_id = Column(Integer, nullable=False, index=True)  # User who owns this post
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


# ==================== Growth Advisor Models ====================


class SEOKeyword(Base):
    """SEO keywords to track for growth monitoring."""
    __tablename__ = "seo_keywords"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    keyword = Column(String(500), nullable=False)
    target_url = Column(String(500), nullable=True)
    category = Column(String(100), nullable=True)  # e.g., "brand", "service", "location"
    priority = Column(String(20), default="medium")  # high, medium, low
    status = Column(String(20), default="active")  # active, paused, negative
    search_volume = Column(Integer, nullable=True)  # Estimated monthly searches
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KeywordRankingCheck(Base):
    """Google SEO ranking check history."""
    __tablename__ = "keyword_ranking_checks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    keyword_id = Column(Integer, nullable=False, index=True)
    keyword = Column(String(500), nullable=False)
    position = Column(Integer, nullable=True)  # Current ranking position
    previous_position = Column(Integer, nullable=True)  # Previous ranking
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)  # Click-through rate
    avg_position = Column(Float, default=0.0)
    search_volume = Column(Integer, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50), default="mock")  # google_api, mock
    created_at = Column(DateTime, default=datetime.utcnow)


class AIVisibilityCheck(Base):
    """AI visibility check history (ChatGPT, DeepSeek)."""
    __tablename__ = "ai_visibility_checks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    keyword_id = Column(Integer, nullable=False, index=True)
    keyword = Column(String(500), nullable=False)
    ai_platform = Column(String(50), nullable=False)  # chatgpt, deepseek
    visibility_score = Column(Integer, default=0)  # 0-100
    is_visible = Column(Boolean, default=False)  # Is our brand mentioned?
    brand_mentioned = Column(String(500), nullable=True)  # Which brand was mentioned
    answer_excerpt = Column(Text, nullable=True)  # Relevant part of AI answer
    competitors_mentioned = Column(Text, nullable=True)  # JSON array of competitors
    checked_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50), default="mock")  # openai_api, deepseek_api, mock
    created_at = Column(DateTime, default=datetime.utcnow)


class GrowthRecommendation(Base):
    """AI-generated growth recommendations."""
    __tablename__ = "growth_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    recommendation_type = Column(String(100), nullable=False)  # content, technical, social, local_seo
    priority = Column(String(20), default="medium")  # high, medium, low
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    action_items = Column(Text, nullable=True)  # JSON array of action steps
    expected_impact = Column(String(100), nullable=True)  # high, medium, low
    status = Column(String(20), default="pending")  # pending, in_progress, completed, dismissed
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    report_date = Column(DateTime, default=datetime.utcnow)  # Which daily report this belongs to
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Competitor(Base):
    """Competitor tracking."""
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    website = Column(String(500), nullable=True)
    mention_count = Column(Integer, default=0)  # Times mentioned in AI
    last_mentioned_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyGrowthReport(Base):
    """Daily growth report summary."""
    __tablename__ = "daily_growth_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    total_keywords = Column(Integer, default=0)
    avg_ranking_position = Column(Float, default=0.0)
    avg_ctr = Column(Float, default=0.0)
    total_impressions = Column(Integer, default=0)
    total_clicks = Column(Integer, default=0)
    chatgpt_visibility_score = Column(Integer, default=0)
    deepseek_visibility_score = Column(Integer, default=0)
    keywords_improved = Column(Integer, default=0)
    keywords_declined = Column(Integer, default=0)
    competitors_mentioned = Column(Integer, default=0)
    top_keyword = Column(String(500), nullable=True)
    top_competitor = Column(String(200), nullable=True)
    summary = Column(Text, nullable=True)
    action_plan = Column(Text, nullable=True)  # JSON array of next steps
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================== Knowledge Base / RAG Models ====================


class Document(Base):
    """Uploaded documents for Knowledge Base RAG."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    document_type = Column(String(100), nullable=True)  # exhibitor_manual, venue_rules, fire_safety, electrical, hanging_signs, labor_rules, booth_design, other
    event_name = Column(String(300), nullable=True)  # CES, NAB, InfoComm, etc.
    venue_name = Column(String(300), nullable=True)
    year = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)  # bytes
    file_path = Column(String(500), nullable=True)  # Storage path
    status = Column(String(50), default="processing")  # processing, indexed, error
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentChunk(Base):
    """Document chunks for RAG retrieval."""
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON with additional metadata
    embedding = Column(Text, nullable=True)  # Vector embedding (stored as JSON string for SQLite compatibility)
    created_at = Column(DateTime, default=datetime.utcnow)


class RAGQuery(Base):
    """RAG query history with answers."""
    __tablename__ = "rag_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)  # JSON array of source documents/chunks
    provider = Column(String(50), default="mock")  # mock, openai, deepseek, nvidia
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================== Compliance Models ====================


class ComplianceProject(Base):
    """Compliance checking project."""
    __tablename__ = "compliance_projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(300), nullable=False)
    event_name = Column(String(300), nullable=True)
    venue_name = Column(String(300), nullable=True)
    booth_size = Column(String(100), nullable=True)  # e.g., "20x20"
    booth_height = Column(Float, nullable=True)
    status = Column(String(50), default="draft")  # draft, checking, passed, failed
    compliance_score = Column(Integer, nullable=True)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ComplianceViolation(Base):
    """Compliance violation records."""
    __tablename__ = "compliance_violations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    rule_name = Column(String(300), nullable=False)
    rule_source = Column(String(200), nullable=True)  # Document reference
    severity = Column(String(20), default="warning")  # critical, warning, info
    description = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


# ==================== Event Workspace Models ====================


class Event(Base):
    """Event workspace for exhibition management."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    event_name = Column(String(500), nullable=False)
    venue = Column(String(500), nullable=True)
    city = Column(String(200), nullable=True)
    country = Column(String(200), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    organizer = Column(String(500), nullable=True)
    website = Column(String(500), nullable=True)
    status = Column(String(50), default="active")  # active, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventDocument(Base):
    """Documents uploaded for specific events."""
    __tablename__ = "event_documents"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=True)
    file_type = Column(String(50), nullable=True)  # pdf, docx, txt
    file_size = Column(Integer, nullable=True)  # bytes
    file_path = Column(String(500), nullable=True)  # Storage path
    document_type = Column(String(100), nullable=True)  # exhibitor_manual, venue_rules, etc.
    status = Column(String(50), default="processing")  # processing, indexed, error
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventDocumentChunk(Base):
    """Document chunks for event RAG retrieval."""
    __tablename__ = "event_document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON with additional metadata
    embedding = Column(Text, nullable=True)  # Vector embedding (stored as JSON string)
    created_at = Column(DateTime, default=datetime.utcnow)


class EventQuery(Base):
    """Event AI Assistant query history."""
    __tablename__ = "event_queries"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)  # JSON array of source documents/chunks
    provider = Column(String(50), default="mock")  # mock, openai, deepseek, nvidia
    created_at = Column(DateTime, default=datetime.utcnow)
