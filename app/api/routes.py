from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import csv
import io

from app.core.database import get_db
from app.models.models import Campaign, GeneratedContent, SocialAccount, ScheduledPost
from app.schemas.schemas import (
    CampaignCreate,
    CampaignResponse,
    GenerationRequest,
    GenerationResponse,
    SocialAccountCreate,
    SocialAccountResponse,
    SchedulePostRequest,
    ScheduledPostResponse,
    PublishNowRequest,
    ContentUpdateRequest,
    ContentTemplateCreate
)
from app.services.content_generator import generate_all_content
from app.services.ai_service import ai_service
from app.services.scheduler import scheduler

router = APIRouter()


# ==================== Campaign Endpoints ====================

@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db)):
    """Create a new marketing campaign."""
    db_campaign = Campaign(
        customer_industry=campaign.customer_industry,
        exhibition_name=campaign.exhibition_name
    )
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    
    return CampaignResponse(
        id=db_campaign.id,
        customer_industry=db_campaign.customer_industry,
        exhibition_name=db_campaign.exhibition_name,
        created_at=db_campaign.created_at,
        updated_at=db_campaign.updated_at,
        contents=[]
    )


@router.get("/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List all campaigns with their generated content."""
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for campaign in campaigns:
        contents = db.query(GeneratedContent).filter(
            GeneratedContent.campaign_id == campaign.id
        ).all()
        result.append(CampaignResponse(
            id=campaign.id,
            customer_industry=campaign.customer_industry,
            exhibition_name=campaign.exhibition_name,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
            contents=contents
        ))
    
    return result


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Get a specific campaign with its content."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    contents = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign.id
    ).all()
    
    return CampaignResponse(
        id=campaign.id,
        customer_industry=campaign.customer_industry,
        exhibition_name=campaign.exhibition_name,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        contents=contents
    )


@router.get("/campaigns/{campaign_id}/export/txt")
async def export_campaign_txt(campaign_id: int, db: Session = Depends(get_db)):
    """Export campaign content as a text file."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    contents = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign.id
    ).all()
    
    # Build text content
    lines = [
        f"Marketing Campaign Export",
        f"=" * 50,
        f"Campaign ID: {campaign.id}",
        f"Industry: {campaign.customer_industry}",
        f"Exhibition: {campaign.exhibition_name}",
        f"Created: {campaign.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"=" * 50,
        f"",
    ]
    
    for content in contents:
        content_type = content.content_type.replace("_", " ").title()
        lines.extend([
            f"[ {content_type} ]",
            f"-" * 40,
            content.content,
            f"",
            f"",
        ])
    
    content = "\n".join(lines)
    
    filename = f"campaign_{campaign_id}_{campaign.exhibition_name.replace(' ', '_')}.txt"
    
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/campaigns/{campaign_id}/export/csv")
async def export_campaign_csv(campaign_id: int, db: Session = Depends(get_db)):
    """Export campaign content as a CSV file."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    contents = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign.id
    ).all()
    
    # Build CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Campaign ID",
        "Industry",
        "Exhibition",
        "Content Type",
        "Content",
        "Created At"
    ])
    
    for content in contents:
        writer.writerow([
            campaign.id,
            campaign.customer_industry,
            campaign.exhibition_name,
            content.content_type,
            content.content,
            content.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    csv_content = output.getvalue()
    filename = f"campaign_{campaign_id}_{campaign.exhibition_name.replace(' ', '_')}.csv"
    
    return StreamingResponse(
        io.BytesIO(csv_content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/generate", response_model=GenerationResponse)
async def generate_content(
    request: GenerationRequest,
    db: Session = Depends(get_db),
    use_ai: bool = Query(True, description="Use AI generation when available"),
    provider: str = Query("auto", description="AI provider: 'openai', 'deepseek', or 'auto'")
):
    """
    Generate marketing content for an exhibition.
    
    Creates a new campaign and generates:
    - LinkedIn post
    - Facebook post
    - Google Business Profile post
    - Image prompts for AI generation
    """
    # Create the campaign
    db_campaign = Campaign(
        customer_industry=request.customer_industry,
        exhibition_name=request.exhibition_name
    )
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    
    # Determine provider
    if provider == "auto":
        provider = ai_service.get_provider_name()
    
    # Try AI generation first if available
    use_ai = use_ai and ai_service.is_available() and provider != "none"
    
    if use_ai:
        try:
            linkedin_post = await ai_service.generate_linkedin_post(
                request.customer_industry,
                request.exhibition_name,
                provider
            )
            facebook_post = await ai_service.generate_facebook_post(
                request.customer_industry,
                request.exhibition_name,
                provider
            )
            google_post = await ai_service.generate_google_business_post(
                request.customer_industry,
                request.exhibition_name,
                provider
            )
            image_prompts = await ai_service.generate_image_prompts(
                request.customer_industry,
                request.exhibition_name,
                provider
            )
        except Exception as e:
            # Fallback to template-based generation on error
            content = generate_all_content(request.customer_industry, request.exhibition_name)
            linkedin_post = content["linkedin_post"]
            facebook_post = content["facebook_post"]
            google_post = content["google_business_post"]
            image_prompts = content["image_prompts"]
    else:
        # Use template-based generation
        content = generate_all_content(request.customer_industry, request.exhibition_name)
        linkedin_post = content["linkedin_post"]
        facebook_post = content["facebook_post"]
        google_post = content["google_business_post"]
        image_prompts = content["image_prompts"]
    
    # Save each content type to database
    content_types = [
        ("linkedin", linkedin_post),
        ("facebook", facebook_post),
        ("google_business", google_post),
        ("image_prompt", "\n---\n".join(image_prompts))
    ]
    
    for content_type, content_text in content_types:
        db_content = GeneratedContent(
            campaign_id=db_campaign.id,
            content_type=content_type,
            content=content_text
        )
        db.add(db_content)
    
    db.commit()
    
    return GenerationResponse(
        campaign_id=db_campaign.id,
        linkedin_post=linkedin_post,
        facebook_post=facebook_post,
        google_business_post=google_post,
        image_prompts=image_prompts
    )


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Delete a campaign and its associated content."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Delete associated content first
    db.query(GeneratedContent).filter(GeneratedContent.campaign_id == campaign_id).delete()
    
    # Delete the campaign
    db.delete(campaign)
    db.commit()
    
    return {"message": "Campaign deleted successfully"}


# ==================== Social Accounts Endpoints ====================

@router.post("/social-accounts", response_model=SocialAccountResponse)
async def create_social_account(
    account: SocialAccountCreate, 
    db: Session = Depends(get_db)
):
    """Create a new social media account connection."""
    db_account = SocialAccount(
        platform=account.platform,
        account_name=account.account_name,
        account_id=account.account_id,
        access_token=account.access_token,
        refresh_token=account.refresh_token,
        token_expires_at=account.token_expires_at
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    
    return SocialAccountResponse(
        id=db_account.id,
        platform=db_account.platform,
        account_name=db_account.account_name,
        account_id=db_account.account_id,
        is_active=db_account.is_active,
        created_at=db_account.created_at,
        updated_at=db_account.updated_at
    )


@router.get("/social-accounts", response_model=list[SocialAccountResponse])
async def list_social_accounts(
    platform: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all social media accounts."""
    query = db.query(SocialAccount)
    if platform:
        query = query.filter(SocialAccount.platform == platform)
    
    accounts = query.order_by(SocialAccount.created_at.desc()).all()
    
    return [
        SocialAccountResponse(
            id=a.id,
            platform=a.platform,
            account_name=a.account_name,
            account_id=a.account_id,
            is_active=a.is_active,
            created_at=a.created_at,
            updated_at=a.updated_at
        )
        for a in accounts
    ]


@router.get("/social-accounts/{account_id}", response_model=SocialAccountResponse)
async def get_social_account(account_id: int, db: Session = Depends(get_db)):
    """Get a specific social media account."""
    account = db.query(SocialAccount).filter(SocialAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Social account not found")
    
    return SocialAccountResponse(
        id=account.id,
        platform=account.platform,
        account_name=account.account_name,
        account_id=account.account_id,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at
    )


@router.delete("/social-accounts/{account_id}")
async def delete_social_account(account_id: int, db: Session = Depends(get_db)):
    """Delete a social media account."""
    account = db.query(SocialAccount).filter(SocialAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Social account not found")
    
    db.delete(account)
    db.commit()
    
    return {"message": "Social account deleted successfully"}


# ==================== Scheduled Posts Endpoints ====================

@router.post("/schedule", response_model=ScheduledPostResponse)
async def schedule_post(
    request: SchedulePostRequest,
    db: Session = Depends(get_db)
):
    """Schedule a post for automatic publishing."""
    db_post = ScheduledPost(
        campaign_id=request.campaign_id,
        content_id=request.content_id,
        platform=request.platform,
        social_account_id=request.social_account_id,
        content=request.content,
        scheduled_at=request.scheduled_at,
        status="scheduled"
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    
    return ScheduledPostResponse(
        id=db_post.id,
        campaign_id=db_post.campaign_id,
        content_id=db_post.content_id,
        platform=db_post.platform,
        social_account_id=db_post.social_account_id,
        content=db_post.content,
        scheduled_at=db_post.scheduled_at,
        published_at=db_post.published_at,
        status=db_post.status,
        platform_post_id=db_post.platform_post_id,
        error_message=db_post.error_message,
        created_at=db_post.created_at
    )


@router.get("/scheduled-posts", response_model=list[ScheduledPostResponse])
async def list_scheduled_posts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all scheduled posts."""
    query = db.query(ScheduledPost)
    
    if platform:
        query = query.filter(ScheduledPost.platform == platform)
    if status:
        query = query.filter(ScheduledPost.status == status)
    
    posts = query.order_by(ScheduledPost.scheduled_at.asc()).all()
    
    return [
        ScheduledPostResponse(
            id=p.id,
            campaign_id=p.campaign_id,
            content_id=p.content_id,
            platform=p.platform,
            social_account_id=p.social_account_id,
            content=p.content,
            scheduled_at=p.scheduled_at,
            published_at=p.published_at,
            status=p.status,
            platform_post_id=p.platform_post_id,
            error_message=p.error_message,
            created_at=p.created_at
        )
        for p in posts
    ]


@router.get("/scheduled-posts/{post_id}", response_model=ScheduledPostResponse)
async def get_scheduled_post(post_id: int, db: Session = Depends(get_db)):
    """Get a specific scheduled post."""
    post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    
    return ScheduledPostResponse(
        id=post.id,
        campaign_id=post.campaign_id,
        content_id=post.content_id,
        platform=post.platform,
        social_account_id=post.social_account_id,
        content=post.content,
        scheduled_at=post.scheduled_at,
        published_at=post.published_at,
        status=post.status,
        platform_post_id=post.platform_post_id,
        error_message=post.error_message,
        created_at=post.created_at
    )


@router.delete("/scheduled-posts/{post_id}")
async def delete_scheduled_post(post_id: int, db: Session = Depends(get_db)):
    """Delete a scheduled post."""
    post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    
    if post.status == "published":
        raise HTTPException(status_code=400, detail="Cannot delete a published post")
    
    db.delete(post)
    db.commit()
    
    return {"message": "Scheduled post deleted successfully"}


@router.post("/publish-now")
async def publish_now(
    request: PublishNowRequest,
    db: Session = Depends(get_db)
):
    """Publish a post immediately to the specified platform."""
    # Get social account if specified
    account = None
    if request.social_account_id:
        account = db.query(SocialAccount).filter(
            SocialAccount.id == request.social_account_id
        ).first()
    
    # Check if mock mode is enabled
    use_mock = account.is_mock_mode if account else True
    
    # Publish based on platform and account configuration
    if request.platform == "linkedin":
        if use_mock:
            from app.services.mock_service import get_mock_service
            service = get_mock_service("linkedin", account.account_name if account else None)
            result = service.post_text(request.content)
        else:
            from app.services.linkedin_service import get_linkedin_service
            access_token = account.access_token if account else None
            service = get_linkedin_service(access_token)
            result = await service.post_text(request.content)
    elif request.platform == "facebook":
        if use_mock:
            from app.services.mock_service import get_mock_service
            service = get_mock_service("facebook", account.account_name if account else None)
            result = service.post_text(request.content)
        else:
            from app.services.facebook_service import get_facebook_service
            access_token = account.access_token if account else None
            page_id = account.account_id if account else None
            service = get_facebook_service(access_token)
            result = await service.post_to_page(request.content, page_id)
    elif request.platform == "google_business":
        if use_mock:
            from app.services.mock_service import get_mock_service
            service = get_mock_service("google_business", account.account_name if account else None)
            result = service.post_text(request.content)
        else:
            from app.services.google_business_service import get_google_business_service
            api_key = account.access_token if account else None
            access_token = account.refresh_token if account else None
            location_id = account.account_id if account else None
            service = get_google_business_service(api_key, access_token)
            result = await service.create_local_post(request.content, location_id)
    else:
        return {"success": False, "error": f"Unknown platform: {request.platform}"}
    
    # Save to scheduled posts for record
    db_post = ScheduledPost(
        platform=request.platform,
        social_account_id=request.social_account_id,
        content=request.content,
        scheduled_at=None,
        published_at=None,
        status="published" if result["success"] else "failed",
        platform_post_id=result.get("post_id"),
        error_message=result.get("error") if not result["success"] else None
    )
    db.add(db_post)
    db.commit()
    
    return result


# ==================== Status Endpoint ====================

@router.get("/status")
async def get_status():
    """Get the status of AI services and scheduler."""
    from app.services.linkedin_service import LinkedInService
    from app.services.facebook_service import FacebookService
    from app.services.google_business_service import GoogleBusinessService
    
    return {
        "ai_available": ai_service.is_available(),
        "ai_provider": ai_service.get_provider_name(),
        "linkedin_configured": LinkedInService().is_configured(),
        "facebook_configured": FacebookService().is_configured(),
        "google_business_configured": GoogleBusinessService().is_configured(),
        "scheduler_running": True,
        "message": "System ready",
        "mock_mode_available": True
    }


# ==================== Content Editing Endpoints ====================

@router.put("/contents/{content_id}")
async def update_content(
    content_id: int,
    request: ContentUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update (edit) generated content."""
    content = db.query(GeneratedContent).filter(
        GeneratedContent.id == content_id
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    content.content = request.content
    db.commit()
    db.refresh(content)
    
    return {
        "success": True,
        "message": "Content updated successfully",
        "content_id": content.id,
        "content_type": content.content_type
    }


@router.get("/campaigns/{campaign_id}/contents")
async def get_campaign_contents(campaign_id: int, db: Session = Depends(get_db)):
    """Get all contents for a campaign with editing capability."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    contents = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign_id
    ).all()
    
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.exhibition_name,
        "industry": campaign.customer_industry,
        "contents": [
            {
                "id": c.id,
                "content_type": c.content_type,
                "content": c.content,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in contents
        ]
    }


# ==================== Content Templates Endpoints ====================

@router.get("/templates")
async def list_templates(
    platform: Optional[str] = None,
    template_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all content templates."""
    from app.models.models import ContentTemplate
    
    query = db.query(ContentTemplate).filter(ContentTemplate.is_active == True)
    
    if platform:
        query = query.filter(ContentTemplate.platform.in_([platform, "all"]))
    if template_type:
        query = query.filter(ContentTemplate.template_type == template_type)
    
    templates = query.all()
    
    return [
        {
            "id": t.id,
            "name": t.name,
            "template_type": t.template_type,
            "platform": t.platform,
            "prompt_template": t.prompt_template
        }
        for t in templates
    ]


@router.post("/templates")
async def create_template(
    request: ContentTemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new content template."""
    from app.models.models import ContentTemplate
    
    db_template = ContentTemplate(
        name=request.name,
        template_type=request.template_type,
        platform=request.platform,
        prompt_template=request.prompt_template,
        is_active=True
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    
    return {
        "success": True,
        "message": "Template created successfully",
        "template_id": db_template.id
    }


@router.post("/templates/init")
async def init_default_templates(db: Session = Depends(get_db)):
    """Initialize default content templates."""
    from app.models.models import ContentTemplate
    
    # Check if templates already exist
    existing = db.query(ContentTemplate).first()
    if existing:
        return {"success": True, "message": "Templates already initialized"}
    
    # Default templates
    default_templates = [
        # Professional Templates
        {
            "name": "Professional LinkedIn",
            "template_type": "professional",
            "platform": "linkedin",
            "prompt_template": "Write a professional LinkedIn post about {industry} exhibition booth design for {exhibition}. Include industry-specific terminology, professional tone, and relevant hashtags."
        },
        {
            "name": "Professional Facebook",
            "template_type": "professional",
            "platform": "facebook",
            "prompt_template": "Write a professional Facebook post announcing our {industry} exhibition booth at {exhibition}. Professional tone with moderate emojis."
        },
        {
            "name": "Professional Google",
            "template_type": "professional",
            "platform": "google_business",
            "prompt_template": "Write a concise Google Business Profile post about our exhibition presence at {exhibition} for the {industry} industry. SEO optimized, local business style."
        },
        
        # Casual Templates
        {
            "name": "Casual LinkedIn",
            "template_type": "casual",
            "platform": "linkedin",
            "prompt_template": "Write a casual, friendly LinkedIn post about our exciting {industry} exhibition booth at {exhibition}. Conversational tone, personal approach."
        },
        {
            "name": "Casual Facebook",
            "template_type": "casual",
            "platform": "facebook",
            "prompt_template": "Write a casual, engaging Facebook post about our booth at {exhibition}. Fun, friendly, community-focused tone with emojis."
        },
        {
            "name": "Casual Google",
            "template_type": "casual",
            "platform": "google_business",
            "prompt_template": "Write a friendly Google Business post about visiting us at {exhibition}! Warm, welcoming tone for local customers."
        },
        
        # Promotional Templates
        {
            "name": "Promotional LinkedIn",
            "template_type": "promotional",
            "platform": "linkedin",
            "prompt_template": "Write a promotional LinkedIn post highlighting our {industry} exhibition booth at {exhibition}. Highlight USPs, special offers, and call-to-action."
        },
        {
            "name": "Promotional Facebook",
            "template_type": "promotional",
            "platform": "facebook",
            "prompt_template": "Write a promotional Facebook post with special exhibition offer for {exhibition}. Exciting, urgent tone with discount mentions."
        },
        {
            "name": "Promotional Google",
            "template_type": "promotional",
            "platform": "google_business",
            "prompt_template": "Write a promotional Google Business post about our exhibition special at {exhibition}. Clear offer, urgency, local SEO optimized."
        },
    ]
    
    for t in default_templates:
        db_template = ContentTemplate(**t)
        db.add(db_template)
    
    db.commit()
    
    return {
        "success": True,
        "message": f"Initialized {len(default_templates)} default templates"
    }


# ==================== Workflow Endpoints ====================

@router.get("/workflow/campaign/{campaign_id}")
async def get_campaign_workflow(campaign_id: int, db: Session = Depends(get_db)):
    """Get the complete workflow status for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get all contents
    contents = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign_id
    ).all()
    
    # Get all scheduled/published posts for this campaign
    posts = db.query(ScheduledPost).filter(
        ScheduledPost.campaign_id == campaign_id
    ).all()
    
    return {
        "campaign": {
            "id": campaign.id,
            "industry": campaign.customer_industry,
            "exhibition": campaign.exhibition_name,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None
        },
        "contents": {
            "total": len(contents),
            "items": [
                {
                    "id": c.id,
                    "type": c.content_type,
                    "length": len(c.content),
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                for c in contents
            ]
        },
        "scheduling": {
            "total": len(posts),
            "scheduled": len([p for p in posts if p.status == "scheduled"]),
            "published": len([p for p in posts if p.status == "published"]),
            "failed": len([p for p in posts if p.status == "failed"])
        },
        "workflow_status": _calculate_workflow_status(contents, posts)
    }


def _calculate_workflow_status(contents, posts):
    """Calculate the workflow status."""
    if not contents:
        return "draft"
    if posts:
        published = [p for p in posts if p.status == "published"]
        scheduled = [p for p in posts if p.status == "scheduled"]
        if published:
            return "completed"
        elif scheduled:
            return "scheduled"
    return "generated"


# ==================== Platform Adapter Endpoints ====================

@router.get("/platforms")
async def list_platforms():
    """Get all available social media platforms with their status."""
    from app.services.platform_adapter import get_all_platform_configs
    
    platforms = get_all_platform_configs()
    configured_count = sum(1 for p in platforms if p["is_configured"] and not p["is_mock"])
    
    return {
        "platforms": platforms,
        "summary": {
            "total": len(platforms),
            "configured": configured_count,
            "mock_mode": len(platforms) - configured_count
        }
    }


@router.post("/publish/batch")
async def publish_to_multiple_platforms(
    request: dict,
    db: Session = Depends(get_db)
):
    """
    Publish content to multiple platforms at once.
    
    Supports all platforms: linkedin, facebook, instagram, x, google_business
    Automatically uses mock mode for unconfigured platforms.
    
    Request body:
    {
        "platforms": ["linkedin", "facebook", "instagram"],
        "content": "Your post content here"
    }
    """
    from app.services.platform_adapter import get_platform_adapter, PlatformType
    
    platforms = request.get("platforms", [])
    content = request.get("content", "")
    
    if not platforms:
        raise HTTPException(status_code=400, detail="At least one platform is required")
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    results = []
    
    for platform_name in platforms:
        try:
            adapter = get_platform_adapter(platform_name)
            result = await adapter.publish(content)
            results.append(result.to_dict())
            
            # Parse published_at if it's a string
            published_at = result.published_at
            if published_at and isinstance(published_at, str):
                published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            
            # Save to scheduled posts for history
            db_post = ScheduledPost(
                platform=platform_name,
                content=content,
                scheduled_at=None,
                published_at=published_at,
                status="published" if result.success else "failed",
                platform_post_id=result.post_id,
                error_message=result.error
            )
            db.add(db_post)
        except ValueError as e:
            results.append({
                "success": False,
                "platform": platform_name,
                "error": str(e)
            })
    
    db.commit()
    
    successful = sum(1 for r in results if r.get("success"))
    return {
        "total": len(platforms),
        "successful": successful,
        "failed": len(platforms) - successful,
        "results": results
    }


@router.post("/publish/{platform}")
async def publish_to_single_platform(
    platform: str,
    content: str,
    db: Session = Depends(get_db)
):
    """Publish content to a single platform."""
    from app.services.platform_adapter import get_platform_adapter
    
    try:
        adapter = get_platform_adapter(platform)
        result = await adapter.publish(content)
        
        # Parse published_at if it's a string
        published_at = result.published_at
        if published_at and isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        
        # Save to scheduled posts for history
        db_post = ScheduledPost(
            platform=platform,
            content=content,
            scheduled_at=None,
            published_at=published_at,
            status="published" if result.success else "failed",
            platform_post_id=result.post_id,
            error_message=result.error
        )
        db.add(db_post)
        db.commit()
        
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Content Optimization Endpoints ====================

@router.post("/optimize")
async def optimize_content(request: dict):
    """
    Optimize content for multiple platforms.
    
    Returns platform-specific optimized versions of the content.
    """
    from app.services.content_optimizer import content_optimizer
    
    content = request.get("content", "")
    platforms = request.get("platforms", [])
    industry = request.get("industry", "")
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    if not platforms:
        raise HTTPException(status_code=400, detail="At least one platform is required")
    
    results = content_optimizer.optimize_batch(content, platforms, industry)
    
    return {
        "original": content,
        "industry": industry,
        "optimizations": {
            platform: {
                "optimized": r.optimized,
                "changes": r.changes,
                "warnings": r.warnings,
                "character_count": r.character_count,
                "character_limit": r.character_limit,
                "remaining": r.character_limit - r.character_count
            }
            for platform, r in results.items()
        }
    }


@router.post("/campaigns/{campaign_id}/optimize")
async def optimize_campaign_content(
    campaign_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    """Optimize and save campaign content for specified platforms."""
    from app.services.content_optimizer import content_optimizer
    from app.models.models import Campaign, GeneratedContent, OptimizedContent
    import json
    
    platforms = request.get("platforms", [])
    
    if not platforms:
        raise HTTPException(status_code=400, detail="At least one platform is required")
    
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get or create base content
    base_content = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign_id,
        GeneratedContent.content_type == "linkedin"  # Use LinkedIn as base
    ).first()
    
    if not base_content:
        raise HTTPException(status_code=400, detail="No base content found. Generate content first.")
    
    # Optimize for each platform
    results = content_optimizer.optimize_batch(
        base_content.content,
        platforms,
        campaign.customer_industry
    )
    
    # Save optimized content
    optimized_ids = {}
    for platform, result in results.items():
        # Check if already exists
        existing = db.query(OptimizedContent).filter(
            OptimizedContent.campaign_id == campaign_id,
            OptimizedContent.platform == platform
        ).first()
        
        if existing:
            existing.optimized_content = result.optimized
            existing.changes = json.dumps(result.changes)
            existing.warnings = json.dumps(result.warnings)
            existing.character_count = result.character_count
            existing.character_limit = result.character_limit
            optimized_ids[platform] = existing.id
        else:
            new_optimized = OptimizedContent(
                campaign_id=campaign_id,
                content_id=base_content.id,
                platform=platform,
                original_content=result.original,
                optimized_content=result.optimized,
                changes=json.dumps(result.changes),
                warnings=json.dumps(result.warnings),
                character_count=result.character_count,
                character_limit=result.character_limit
            )
            db.add(new_optimized)
            db.flush()
            optimized_ids[platform] = new_optimized.id
    
    # Update campaign status
    campaign.status = "optimized"
    campaign.selected_platforms = json.dumps(platforms)
    
    db.commit()
    
    return {
        "success": True,
        "campaign_id": campaign_id,
        "platforms": platforms,
        "optimized_count": len(optimized_ids),
        "optimizations": {
            platform: {
                "id": opt_id,
                "optimized": results[platform].optimized,
                "changes": results[platform].changes
            }
            for platform, opt_id in optimized_ids.items()
        }
    }


@router.get("/campaigns/{campaign_id}/optimized")
async def get_campaign_optimized_content(campaign_id: int, db: Session = Depends(get_db)):
    """Get all optimized content for a campaign."""
    from app.models.models import Campaign, OptimizedContent
    import json
    
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    optimized_contents = db.query(OptimizedContent).filter(
        OptimizedContent.campaign_id == campaign_id
    ).all()
    
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.exhibition_name,
        "industry": campaign.customer_industry,
        "status": campaign.status,
        "selected_platforms": json.loads(campaign.selected_platforms) if campaign.selected_platforms else [],
        "optimized_contents": [
            {
                "id": oc.id,
                "platform": oc.platform,
                "original": oc.original_content,
                "optimized": oc.optimized_content,
                "changes": json.loads(oc.changes) if oc.changes else [],
                "warnings": json.loads(oc.warnings) if oc.warnings else [],
                "character_count": oc.character_count,
                "character_limit": oc.character_limit
            }
            for oc in optimized_contents
        ]
    }


# ==================== Preview and Publish Endpoints ====================

@router.post("/campaigns/{campaign_id}/preview")
async def preview_publish(
    campaign_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    """
    Preview what will be published to each platform.
    Does not publish, just returns the optimized content.
    """
    from app.services.content_optimizer import content_optimizer
    from app.models.models import Campaign, GeneratedContent, OptimizedContent
    import json
    
    platforms = request.get("platforms", [])
    
    if not platforms:
        raise HTTPException(status_code=400, detail="At least one platform is required")
    
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get base content
    base_content = db.query(GeneratedContent).filter(
        GeneratedContent.campaign_id == campaign_id,
        GeneratedContent.content_type == "linkedin"
    ).first()
    
    if not base_content:
        raise HTTPException(status_code=400, detail="No content found")
    
    # Check for existing optimized content
    existing_optimized = db.query(OptimizedContent).filter(
        OptimizedContent.campaign_id == campaign_id
    ).all()
    existing_map = {oc.platform: oc for oc in existing_optimized}
    
    # Get or generate optimized content
    previews = []
    for platform in platforms:
        if platform in existing_map:
            oc = existing_map[platform]
            previews.append({
                "platform": platform,
                "content": oc.optimized_content,
                "is_existing": True,
                "character_count": oc.character_count,
                "character_limit": oc.character_limit
            })
        else:
            result = content_optimizer.optimize(
                base_content.content, platform, campaign.customer_industry
            )
            previews.append({
                "platform": platform,
                "content": result.optimized,
                "is_existing": False,
                "character_count": result.character_count,
                "character_limit": result.character_limit,
                "changes": result.changes,
                "warnings": result.warnings
            })
    
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.exhibition_name,
        "industry": campaign.customer_industry,
        "preview_count": len(previews),
        "previews": previews
    }


@router.post("/campaigns/{campaign_id}/publish")
async def publish_campaign(
    campaign_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    """
    Publish campaign content to specified platforms.
    
    If publish_now is True, publishes immediately.
    Otherwise, schedules for the specified time.
    """
    from app.models.models import Campaign, OptimizedContent, ScheduledPost
    from datetime import datetime
    import json
    
    platforms = request.get("platforms", [])
    publish_now = request.get("publish_now", True)
    scheduled_at = request.get("scheduled_at")
    
    if not platforms:
        raise HTTPException(status_code=400, detail="At least one platform is required")
    
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get optimized content
    optimized_contents = db.query(OptimizedContent).filter(
        OptimizedContent.campaign_id == campaign_id
    ).all()
    optimized_map = {oc.platform: oc for oc in optimized_contents}
    
    results = []
    for platform in platforms:
        if platform not in optimized_map:
            results.append({
                "platform": platform,
                "success": False,
                "error": "No optimized content found. Run optimization first."
            })
            continue
        
        oc = optimized_map[platform]
        
        # Create scheduled post entry
        post = ScheduledPost(
            campaign_id=campaign_id,
            optimized_content_id=oc.id,
            platform=platform,
            content=oc.optimized_content,
            status="draft",
            created_at=datetime.utcnow()
        )
        db.add(post)
        db.flush()
        
        if publish_now:
            # Publish immediately - use sync version
            from app.services.platform_adapter import get_platform_adapter
            
            try:
                adapter = get_platform_adapter(post.platform)
                result = adapter.publish_sync(post.content)
                
                post.status = "published" if result.success else "failed"
                post.published_at = datetime.utcnow() if result.success else None
                post.platform_post_id = result.post_id
                post.url = result.url
                post.is_mock = result.is_mock
                post.error_message = result.error if not result.success else None
                
                results.append({
                    "platform": platform,
                    "success": result.success,
                    "post_id": post.id,
                    "status": post.status,
                    "platform_post_id": result.post_id,
                    "url": result.url,
                    "is_mock": result.is_mock,
                    "error": result.error if not result.success else None
                })
            except Exception as e:
                post.status = "failed"
                post.error_message = str(e)
                results.append({
                    "platform": platform,
                    "success": False,
                    "post_id": post.id,
                    "status": "failed",
                    "error": str(e)
                })
        else:
            # Schedule for later
            if scheduled_at:
                sched_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            else:
                # Default to 1 hour from now
                sched_time = datetime.utcnow() + timedelta(hours=1)
            
            from app.services.scheduler_service import scheduler_service
            success = scheduler_service.schedule_post(post.id, sched_time)
            
            results.append({
                "platform": platform,
                "success": success,
                "post_id": post.id,
                "status": "scheduled" if success else "draft",
                "scheduled_at": sched_time.isoformat() if success else None
            })
    
    # Update campaign status
    campaign.status = "publishing" if publish_now else "scheduled"
    db.commit()
    
    return {
        "campaign_id": campaign_id,
        "publish_mode": "immediate" if publish_now else "scheduled",
        "total": len(platforms),
        "successful": sum(1 for r in results if r.get("success")),
        "results": results
    }


# ==================== Settings Endpoints ====================

@router.get("/settings/social-accounts")
async def get_social_accounts(db: Session = Depends(get_db)):
    """Get all social media account configurations."""
    from app.models.models import SocialAccount
    
    accounts = db.query(SocialAccount).all()
    
    return {
        "accounts": [
            {
                "id": acc.id,
                "platform": acc.platform,
                "account_name": acc.account_name,
                "account_id": acc.account_id,
                "is_active": acc.is_active,
                "is_mock_mode": acc.is_mock_mode,
                "has_token": bool(acc.access_token),
                "has_api_key": bool(acc.api_key),
                "created_at": acc.created_at.isoformat() if acc.created_at else None
            }
            for acc in accounts
        ]
    }


@router.post("/settings/social-accounts")
async def save_social_account(
    request: dict,
    db: Session = Depends(get_db)
):
    """Save or update a social media account configuration."""
    from app.models.models import SocialAccount
    from datetime import datetime
    
    platform = request.get("platform")
    account_name = request.get("account_name")
    account_id = request.get("account_id")
    access_token = request.get("access_token")
    api_key = request.get("api_key")
    is_mock_mode = request.get("is_mock_mode", True)
    
    if not platform or not account_name:
        raise HTTPException(status_code=400, detail="Platform and account name are required")
    
    existing = db.query(SocialAccount).filter(
        SocialAccount.platform == platform
    ).first()
    
    if existing:
        existing.account_name = account_name
        existing.account_id = account_id
        if access_token:
            existing.access_token = access_token
        if api_key:
            existing.api_key = api_key
        existing.is_mock_mode = is_mock_mode
        existing.updated_at = datetime.utcnow()
        account = existing
    else:
        account = SocialAccount(
            platform=platform,
            account_name=account_name,
            account_id=account_id,
            access_token=access_token,
            api_key=api_key,
            is_mock_mode=is_mock_mode
        )
        db.add(account)
    
    db.commit()
    db.refresh(account)
    
    return {
        "success": True,
        "id": account.id,
        "platform": account.platform,
        "is_mock_mode": account.is_mock_mode,
        "message": "Account saved successfully"
    }


@router.delete("/settings/social-accounts/{account_id}")
async def delete_social_account(account_id: int, db: Session = Depends(get_db)):
    """Delete a social media account configuration."""
    from app.models.models import SocialAccount
    
    account = db.query(SocialAccount).filter(SocialAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    db.delete(account)
    db.commit()
    
    return {"success": True, "message": "Account deleted"}


@router.get("/settings/platforms-status")
async def get_platforms_status():
    """Get the configuration status of all platforms."""
    from app.services.platform_adapter import get_all_platform_configs
    from app.models.models import SocialAccount
    from app.core.database import SessionLocal
    
    platforms = get_all_platform_configs()
    db = SessionLocal()
    
    accounts = db.query(SocialAccount).all()
    account_map = {acc.platform: acc for acc in accounts}
    db.close()
    
    status = []
    for platform in platforms:
        account = account_map.get(platform["id"])
        status.append({
            "id": platform["id"],
            "name": platform["name"],
            "icon": platform["icon"],
            "color": platform["color"],
            "character_limit": platform["character_limit"],
            "supports_images": platform["supports_images"],
            "is_configured": platform["is_configured"] and not platform["is_mock"],
            "is_mock_mode": platform["is_mock"] or (account.is_mock_mode if account else True),
            "has_credentials": bool(account.access_token if account else None),
            "account_name": account.account_name if account else None
        })
    
    return {"platforms": status}
