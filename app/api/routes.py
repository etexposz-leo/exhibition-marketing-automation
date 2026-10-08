from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import csv
import io

from app.core.database import get_db
from app.core.dependencies import get_current_user
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
from app.services.publishing import prepare_post, immediate, execute_post, post_result, owned, process_post
from app.core.credentials import CredentialStore, has_credentials, remove_credentials

router = APIRouter()


def require_sms_verified(request: Request) -> int:
    from app.core.dependencies import require_verified_session
    return require_verified_session(request)


# ==================== Campaign Endpoints ====================


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(campaign: CampaignCreate, request: Request, db: Session = Depends(get_db)):
    """Create a new marketing campaign."""
    user_id = require_sms_verified(request)
    
    db_campaign = Campaign(
        user_id=user_id,
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
async def list_campaigns(request: Request, skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """List all campaigns with their generated content for current user."""
    user_id = require_sms_verified(request)
    
    campaigns = db.query(Campaign).filter(
        Campaign.user_id == user_id
    ).order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()
    
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
    request: Request,
    gen_request: GenerationRequest,
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
    user_id = require_sms_verified(request)
    
    # Create the campaign
    db_campaign = Campaign(
        user_id=user_id,
        customer_industry=gen_request.customer_industry,
        exhibition_name=gen_request.exhibition_name
    )
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    
    # Determine provider
    if provider == "auto":
        provider = ai_service.get_provider_name()
    
    from app.services import sales_copy as sales, sales_copy_store
    from app.models.models import SalesBrief
    import json
    brief_payload = sales.analyze(sales.Brief(target_audience=gen_request.customer_industry+' exhibitors',
        industry=gen_request.customer_industry, trade_show=gen_request.exhibition_name))
    brief_row = SalesBrief(user_id=user_id,campaign_id=db_campaign.id,payload=json.dumps(brief_payload))
    db.add(brief_row); db.flush()
    mode = 'ai' if use_ai and ai_service.is_available() and provider != 'none' else 'local'
    generated = {}
    for platform in ('linkedin','facebook','google_business'):
        if mode == 'ai':
            try:
                generated[platform] = await ai_service.generate_content(sales.ai_prompt(brief_payload,platform),provider=provider)
            except Exception:
                db.rollback()
                raise HTTPException(502,'AI drafting failed; no silent template fallback') from None
        else:
            generated[platform] = sales.generate_local(brief_payload,platform)
        sales_copy_store.create_copy(db,brief_row,platform,generated[platform],mode)
    linkedin_post,facebook_post,google_post = (generated[p] for p in ('linkedin','facebook','google_business'))
    image_prompts = generate_all_content(gen_request.customer_industry,gen_request.exhibition_name)['image_prompts']

    # Save each content type to database
    content_types = [
        ("linkedin", linkedin_post),
        ("facebook", facebook_post),
        ("google_business", google_post),
        ("image_prompt", "\n---\n".join(image_prompts))
    ]
    
    for content_type, content_text in content_types:
        db_content = GeneratedContent(
            user_id=user_id,
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
    from app.models.models import OptimizedContent
    for post in db.query(ScheduledPost).filter(ScheduledPost.campaign_id == campaign_id).all():
        if post.status in {'draft', 'scheduled'}:
            post.status = 'cancelled'
        post.campaign_id = None
        post.optimized_content_id = None
    db.query(OptimizedContent).filter(OptimizedContent.campaign_id == campaign_id).delete()
    db.query(GeneratedContent).filter(GeneratedContent.campaign_id == campaign_id).delete()
    
    # Delete the campaign
    db.delete(campaign)
    db.commit()
    
    return {"message": "Campaign deleted successfully"}


# ==================== Social Accounts Endpoints ====================

@router.post("/social-accounts", response_model=SocialAccountResponse)
async def create_social_account(account: SocialAccountCreate, db: Session = Depends(get_db)):
    row = store_account(db, account.model_dump(), create=True)
    return SocialAccountResponse.model_validate(row)



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
            is_active=a.is_active, is_mock_mode=a.is_mock_mode,
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
        is_active=account.is_active, is_mock_mode=account.is_mock_mode,
        created_at=account.created_at,
        updated_at=account.updated_at
    )


@router.delete("/social-accounts/{account_id}")
async def delete_social_account(account_id: int, db: Session = Depends(get_db)):
    owner = db.info['owner_id']
    account = owned(db, SocialAccount, account_id, owner)
    if account.account_type == 'member' and account.platform == 'linkedin':
        raise HTTPException(409, 'Use LinkedIn disconnect to preserve account and publishing history')
    remove_credentials(db, owner, f'account:{account.id}')
    db.query(ScheduledPost).filter(ScheduledPost.social_account_id == account_id,
        ScheduledPost.status.in_(['draft', 'scheduled'])).update({'status': 'cancelled'})
    db.delete(account)
    db.commit()
    return {'success': True, 'message': 'Account deleted'}



# ==================== Scheduled Posts Endpoints ====================

@router.post("/schedule", response_model=ScheduledPostResponse)
async def schedule_post(request_body: SchedulePostRequest, req: Request, db: Session = Depends(get_db)):
    post = prepare_post(db, db.info['owner_id'], request_body.model_dump(), schedule=True)
    db.commit()
    return scheduled_response(post)



@router.get("/scheduled-posts", response_model=list[ScheduledPostResponse])
async def list_scheduled_posts(
    request: Request,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all scheduled posts."""
    user_id = require_sms_verified(request)
    
    query = db.query(ScheduledPost).filter(ScheduledPost.user_id == user_id)
    
    if platform:
        query = query.filter(ScheduledPost.platform == platform)
    if status:
        query = query.filter(ScheduledPost.status == status)
    
    posts = query.order_by(ScheduledPost.created_at.desc()).all()
    
    return [scheduled_response(p) for p in posts]


@router.get("/scheduled-posts/{post_id}", response_model=ScheduledPostResponse)
async def get_scheduled_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """Get a specific scheduled post."""
    user_id = require_sms_verified(request)
    
    post = db.query(ScheduledPost).filter(
        ScheduledPost.id == post_id,
        ScheduledPost.user_id == user_id
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    
    return scheduled_response(post)


@router.delete("/scheduled-posts/{post_id}")
async def delete_scheduled_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a scheduled post."""
    user_id = require_sms_verified(request)
    
    post = db.query(ScheduledPost).filter(
        ScheduledPost.id == post_id,
        ScheduledPost.user_id == user_id
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    
    if post.execution_mode == 'REAL':
        if post.status in {'processing', 'published', 'reconciliation_required'}:
            raise HTTPException(409, 'Retain real publishing history; reconcile uncertain jobs separately')
        post.status = 'cancelled'
        db.commit()
        return {'message': 'Job cancelled; idempotency history retained'}
    if post.status == "published":
        raise HTTPException(status_code=400, detail="Cannot delete a published post")
    
    db.delete(post)
    db.commit()
    
    return {"message": "Scheduled post deleted successfully"}


@router.post("/publish-now")
async def publish_now(request_body: PublishNowRequest, req: Request, db: Session = Depends(get_db)):
    return await immediate(db, db.info['owner_id'], request_body.model_dump())



# ==================== Status Endpoint ====================

@router.get("/status")
async def get_status():
    return {'scheduler_running': scheduler._running, 'real_publishing_enabled': False,
            'message': 'Phase 1: explicit MOCK / TEST only'}



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
async def publish_to_multiple_platforms(request: dict, db: Session = Depends(get_db)):
    platforms = request.get('platforms', [])
    if request.get('execution_mode') == 'REAL' and platforms != ['linkedin']:
        raise HTTPException(403, 'Only one LinkedIn target is allowed')
    if not platforms:
        raise HTTPException(400, 'Platforms required')
    posts = [prepare_post(db, db.info['owner_id'], {**request, 'platform': platform}) for platform in platforms]
    results = []
    for post in posts:
        results.append(await process_post(db, post))
    db.commit()
    return {'execution_mode': request['execution_mode'], 'simulated': request['execution_mode'] != 'REAL', 'total': len(results),
            'successful': sum(x['success'] for x in results), 'results': results}



@router.post("/publish/{platform}")
async def publish_to_single_platform(platform: str, content: str, execution_mode: str, db: Session = Depends(get_db)):
    return await immediate(db, db.info['owner_id'], dict(platform=platform, content=content, execution_mode=execution_mode))



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
async def publish_campaign(campaign_id: int, request: dict, db: Session = Depends(get_db)):
    from app.models.models import OptimizedContent
    owner = db.info['owner_id']
    campaign = owned(db, Campaign, campaign_id, owner)
    platforms = request.get('platforms', [])
    if request.get('execution_mode') == 'REAL' and platforms != ['linkedin']:
        raise HTTPException(403, 'Only one LinkedIn target is allowed')
    if not platforms:
        raise HTTPException(400, 'Platforms required')
    posts = []
    schedule = not request.get('publish_now', True)
    for platform in platforms:
        content = db.query(OptimizedContent).filter_by(campaign_id=campaign_id, platform=platform).first()
        if content is None:
            raise HTTPException(400, 'Optimized content required for each platform')
        posts.append(prepare_post(db, owner, {**request, 'campaign_id': campaign_id,
            'content_id': content.id, 'platform': platform, 'content': content.optimized_content}, schedule=schedule))
    results = []
    for post in posts:
        if not schedule:
            await process_post(db, post)
        results.append(post_result(post))
    campaign.status = 'scheduled' if schedule else (('completed' if request['execution_mode'] == 'REAL' else 'simulated') if all(x['success'] for x in results) else 'failed')
    db.commit()
    return {'campaign_id': campaign_id, 'execution_mode': request['execution_mode'], 'simulated': request['execution_mode'] != 'REAL',
            'results': results, 'total': len(results), 'successful': sum(x['success'] for x in results)}



# ==================== Settings Endpoints ====================

@router.get("/settings/social-accounts")
async def get_social_accounts(db: Session = Depends(get_db)):
    return {'accounts': [dict(id=a.id, platform=a.platform, account_name=a.account_name,
        account_id=a.account_id, is_active=a.is_active, is_mock_mode=a.is_mock_mode,
        has_token=has_credentials(db, db.info['owner_id'], f'account:{a.id}'),
        has_api_key=False, created_at=a.created_at) for a in db.query(SocialAccount).all()]}



@router.post("/settings/social-accounts")
async def save_social_account(request: dict, db: Session = Depends(get_db)):
    row = store_account(db, request)
    return {'success': True, 'id': row.id, 'platform': row.platform, 'is_mock_mode': row.is_mock_mode}



@router.delete("/settings/social-accounts/{account_id}")
async def delete_social_account(account_id: int, db: Session = Depends(get_db)):
    owner = db.info['owner_id']
    account = owned(db, SocialAccount, account_id, owner)
    if account.account_type == 'member' and account.platform == 'linkedin':
        raise HTTPException(409, 'Use LinkedIn disconnect to preserve account and publishing history')
    remove_credentials(db, owner, f'account:{account.id}')
    db.query(ScheduledPost).filter(ScheduledPost.social_account_id == account_id,
        ScheduledPost.status.in_(['draft', 'scheduled'])).update({'status': 'cancelled'})
    db.delete(account)
    db.commit()
    return {'success': True, 'message': 'Account deleted'}



@router.post("/settings/api-keys")
async def save_api_key(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    if data.get('service') not in {'openai', 'deepseek'} or not data.get('api_key'):
        raise HTTPException(400, 'Service and key required')
    CredentialStore().put(db, db.info['owner_id'], 'ai:' + data['service'], 'api_key', data['api_key'])
    db.commit()
    return {'success': True, 'message': 'Encrypted key stored; provider activation deferred'}



@router.get("/settings/platforms-status")
async def get_platforms_status(db: Session = Depends(get_db)):
    from app.services.platform_adapter import get_all_platform_configs
    accounts = {a.platform: a for a in db.query(SocialAccount).all()}
    result = []
    for item in get_all_platform_configs():
        acc = accounts.get(item['id'])
        item.update(is_mock_mode=bool(acc and acc.is_mock_mode), real_enabled=False,
                    has_credentials=bool(acc and has_credentials(db, db.info['owner_id'], f'account:{acc.id}')),
                    account_name=acc.account_name if acc else None)
        result.append(item)
    return {'platforms': result}



def scheduled_response(post):
    return ScheduledPostResponse(id=post.id, campaign_id=post.campaign_id,
        content_id=post.optimized_content_id, platform=post.platform,
        social_account_id=post.social_account_id, content=post.content,
        scheduled_at=post.scheduled_at, published_at=post.published_at,
        status=post.status, platform_post_id=post.platform_post_id,
        error_message=post.error_message, created_at=post.created_at, updated_at=post.updated_at,
        execution_mode=post.execution_mode, is_mock=post.is_mock, url=post.url, attempt_count=post.attempt_count,
        idempotency_key=post.idempotency_key, timezone=post.source_timezone,
        last_attempt_at=post.last_attempt_at, next_retry_at=post.next_retry_at)


def store_account(db, data, create=False):
    from app.services.platform_adapter import PlatformType
    platform = PlatformType(data.get('platform')).value
    owner = db.info['owner_id']
    if not data.get('account_name'):
        raise HTTPException(400, 'Account name required')
    row = None
    if data.get('id') is not None:
        row = owned(db, SocialAccount, data['id'], owner)
        if row.platform != platform:
            raise HTTPException(400, 'Account platform cannot change')
    elif not create:
        row = db.query(SocialAccount).filter_by(platform=platform).first()
    if row is None:
        row = SocialAccount(user_id=owner, platform=platform)
        db.add(row)
    if row.connection_status == 'connected':
        raise HTTPException(409, 'OAuth-bound account must be managed through LinkedIn connection settings')
    row.account_name = data['account_name']
    row.account_id = data.get('account_id')
    row.is_mock_mode = bool(data.get('is_mock_mode', False))
    row.token_expires_at = data.get('token_expires_at')
    db.flush()
    for kind in ('access_token', 'refresh_token', 'api_key'):
        if data.get(kind):
            CredentialStore().put(db, owner, f'account:{row.id}', kind, data[kind])
    db.commit()
    db.refresh(row)
    return row


@router.post('/settings/test-connection')
async def test_connection(data: dict, db: Session = Depends(get_db)):
    service = data.get('service')
    if service not in {'openai', 'deepseek', 'linkedin', 'facebook', 'instagram', 'x', 'google_business'}:
        raise HTTPException(400, 'Unknown service')
    if data.get('execution_mode') != 'TEST':
        raise HTTPException(403, 'Only local TEST validation available in Phase 1')
    scope = 'ai:' + service
    if service not in {'openai', 'deepseek'}:
        account = db.query(SocialAccount).filter_by(platform=service).first()
        scope = f'account:{account.id}' if account else 'missing'
    return {'success': False, 'execution_mode': 'TEST', 'is_test': True, 'is_mock': False,
            'provider_contacted': False, 'connection_verified': False,
            'credentials_present': has_credentials(db, db.info['owner_id'], scope),
            'message': 'Local configuration check only; provider connection NOT VERIFIED'}
