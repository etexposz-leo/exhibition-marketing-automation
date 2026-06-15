from pydantic import BaseModel
from datetime import datetime
from typing import Optional


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
    is_mock_mode: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Scheduled Post Schemas
class SchedulePostRequest(BaseModel):
    campaign_id: Optional[int] = None
    content_id: Optional[int] = None
    platform: str  # linkedin, facebook, google_business
    social_account_id: Optional[int] = None
    content: str
    scheduled_at: Optional[datetime] = None


class ScheduledPostResponse(BaseModel):
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
