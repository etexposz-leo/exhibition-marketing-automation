from pydantic import BaseModel, field_serializer
from datetime import datetime, timezone
from typing import Optional, Literal


class CampaignCreate(BaseModel):
    customer_industry: str
    exhibition_name: str


class GeneratedContentResponse(BaseModel):
    id: int
    campaign_id: int
    content_type: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class CampaignResponse(BaseModel):
    id: int
    customer_industry: str
    exhibition_name: str
    created_at: datetime
    updated_at: datetime
    contents: list[GeneratedContentResponse] = []

    class Config:
        from_attributes = True


class GenerationRequest(BaseModel):
    customer_industry: str
    exhibition_name: str


class GenerationResponse(BaseModel):
    campaign_id: int
    linkedin_post: str
    facebook_post: str
    google_business_post: str
    image_prompts: list[str]


# Social Account Schemas
class SocialAccountCreate(BaseModel):
    platform: str  # linkedin, facebook, google_business
    account_name: str
    account_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    is_mock_mode: bool = False  # Enable mock posting mode


class SocialAccountResponse(BaseModel):
    id: int
    platform: str
    account_name: str
    account_id: Optional[str]
    is_active: bool
    is_mock_mode: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Scheduled Post Schemas
class SchedulePostRequest(BaseModel):
    execution_mode: Literal["MOCK", "TEST", "REAL"]
    idempotency_key: Optional[str] = None
    timezone: Optional[str] = None
    campaign_id: Optional[int] = None
    content_id: Optional[int] = None
    platform: str  # linkedin, facebook, google_business
    social_account_id: Optional[int] = None
    content: str
    scheduled_at: Optional[datetime] = None


class ScheduledPostResponse(BaseModel):
    idempotency_key: Optional[str] = None
    timezone: Optional[str] = None
    last_attempt_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    execution_mode: str
    is_mock: bool
    url: Optional[str] = None
    attempt_count: int
    updated_at: datetime

    @field_serializer('scheduled_at', 'published_at', 'created_at', 'updated_at', 'last_attempt_at', 'next_retry_at')
    def serialize_utc(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None

    id: int
    campaign_id: Optional[int]
    content_id: Optional[int]
    platform: str
    social_account_id: Optional[int]
    content: str
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    status: str
    platform_post_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PublishNowRequest(BaseModel):
    campaign_id: Optional[int] = None
    content_id: Optional[int] = None
    execution_mode: Literal["MOCK", "TEST", "REAL"]
    idempotency_key: Optional[str] = None
    timezone: Optional[str] = None
    platform: str
    social_account_id: Optional[int] = None
    content: str


# Content Template Schemas
class ContentTemplateCreate(BaseModel):
    name: str
    template_type: str  # professional, casual, promotional
    platform: str  # linkedin, facebook, google_business, all
    prompt_template: str


class ContentTemplateResponse(BaseModel):
    id: int
    name: str
    template_type: str
    platform: str
    prompt_template: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Content Edit Schema
class ContentUpdateRequest(BaseModel):
    content: str
