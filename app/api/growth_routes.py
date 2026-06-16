"""
Growth Advisor API Routes

Endpoints for SEO keyword management, AI visibility monitoring,
and growth recommendations.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.models.models import SEOKeyword, Competitor
from app.services.growth_advisor import get_growth_advisor

router = APIRouter(prefix="/growth", tags=["growth"])


def require_sms_verified(request: Request) -> int:
    """Require user to be authenticated and SMS verified. Returns user_id."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not request.session.get("sms_verified"):
        raise HTTPException(status_code=403, detail="Phone verification required")
    return user_id


# ==================== Pydantic Models ====================

class KeywordCreate(BaseModel):
    keyword: str
    target_url: Optional[str] = None
    category: Optional[str] = None
    priority: str = "medium"
    search_volume: Optional[int] = None


class KeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    target_url: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    search_volume: Optional[int] = None


class KeywordResponse(BaseModel):
    id: int
    keyword: str
    target_url: Optional[str]
    category: Optional[str]
    priority: str
    status: str
    search_volume: Optional[int]
    created_at: datetime
    updated_at: datetime


class CompetitorCreate(BaseModel):
    name: str
    website: Optional[str] = None


class CompetitorResponse(BaseModel):
    id: int
    name: str
    website: Optional[str]
    mention_count: int
    last_mentioned_at: Optional[datetime]
    is_active: bool
    created_at: datetime


class CheckNowResponse(BaseModel):
    success: bool
    google_seo_count: int
    chatgpt_count: int
    deepseek_count: int
    perplexity_count: int
    recommendations_count: int
    report_id: Optional[int]


class ReportResponse(BaseModel):
    id: int
    date: str
    total_keywords: int
    avg_position: float
    avg_ctr: float
    total_impressions: int
    total_clicks: int
    chatgpt_score: int
    deepseek_score: int
    perplexity_score: int
    keywords_improved: int
    keywords_declined: int
    competitors_mentioned: int
    top_keyword: Optional[str]
    top_competitor: Optional[str]
    summary: str
    action_plan: List[str]


class RecommendationResponse(BaseModel):
    id: int
    type: str
    priority: str
    title: str
    description: str
    action_items: List[str]
    impact: str
    status: str
    created_at: str


# ==================== Keyword Endpoints ====================

@router.get("/keywords", response_model=List[KeywordResponse])
async def list_keywords(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all keywords for the current user."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    query = db.query(SEOKeyword).filter(SEOKeyword.user_id == user_id)
    
    if status:
        query = query.filter(SEOKeyword.status == status)
    
    keywords = query.order_by(SEOKeyword.created_at.desc()).all()
    
    return [
        KeywordResponse(
            id=k.id,
            keyword=k.keyword,
            target_url=k.target_url,
            category=k.category,
            priority=k.priority,
            status=k.status,
            search_volume=k.search_volume,
            created_at=k.created_at,
            updated_at=k.updated_at
        )
        for k in keywords
    ]


@router.post("/keywords", response_model=KeywordResponse)
async def create_keyword(
    keyword: KeywordCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new keyword to track."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_keyword = SEOKeyword(
        user_id=user_id,
        keyword=keyword.keyword,
        target_url=keyword.target_url,
        category=keyword.category,
        priority=keyword.priority,
        search_volume=keyword.search_volume,
        status="active"
    )
    
    db.add(db_keyword)
    db.commit()
    db.refresh(db_keyword)
    
    return KeywordResponse(
        id=db_keyword.id,
        keyword=db_keyword.keyword,
        target_url=db_keyword.target_url,
        category=db_keyword.category,
        priority=db_keyword.priority,
        status=db_keyword.status,
        search_volume=db_keyword.search_volume,
        created_at=db_keyword.created_at,
        updated_at=db_keyword.updated_at
    )


@router.put("/keywords/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: int,
    keyword: KeywordUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update a keyword."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_keyword = db.query(SEOKeyword).filter(
        SEOKeyword.id == keyword_id,
        SEOKeyword.user_id == user_id
    ).first()
    
    if not db_keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    # Update fields if provided
    if keyword.keyword is not None:
        db_keyword.keyword = keyword.keyword
    if keyword.target_url is not None:
        db_keyword.target_url = keyword.target_url
    if keyword.category is not None:
        db_keyword.category = keyword.category
    if keyword.priority is not None:
        db_keyword.priority = keyword.priority
    if keyword.status is not None:
        db_keyword.status = keyword.status
    if keyword.search_volume is not None:
        db_keyword.search_volume = keyword.search_volume
    
    db_keyword.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_keyword)
    
    return KeywordResponse(
        id=db_keyword.id,
        keyword=db_keyword.keyword,
        target_url=db_keyword.target_url,
        category=db_keyword.category,
        priority=db_keyword.priority,
        status=db_keyword.status,
        search_volume=db_keyword.search_volume,
        created_at=db_keyword.created_at,
        updated_at=db_keyword.updated_at
    )


@router.delete("/keywords/{keyword_id}")
async def delete_keyword(
    keyword_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a keyword."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_keyword = db.query(SEOKeyword).filter(
        SEOKeyword.id == keyword_id,
        SEOKeyword.user_id == user_id
    ).first()
    
    if not db_keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    db.delete(db_keyword)
    db.commit()
    
    return {"success": True, "message": "Keyword deleted"}


# ==================== Competitor Endpoints ====================

@router.get("/competitors", response_model=List[CompetitorResponse])
async def list_competitors(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all competitors for the current user."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    competitors = db.query(Competitor).filter(
        Competitor.user_id == user_id,
        Competitor.is_active == True
    ).order_by(Competitor.name).all()
    
    return [
        CompetitorResponse(
            id=c.id,
            name=c.name,
            website=c.website,
            mention_count=c.mention_count,
            last_mentioned_at=c.last_mentioned_at,
            is_active=c.is_active,
            created_at=c.created_at
        )
        for c in competitors
    ]


@router.post("/competitors", response_model=CompetitorResponse)
async def create_competitor(
    competitor: CompetitorCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Add a new competitor to track."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_competitor = Competitor(
        user_id=user_id,
        name=competitor.name,
        website=competitor.website,
        is_active=True
    )
    
    db.add(db_competitor)
    db.commit()
    db.refresh(db_competitor)
    
    return CompetitorResponse(
        id=db_competitor.id,
        name=db_competitor.name,
        website=db_competitor.website,
        mention_count=db_competitor.mention_count,
        last_mentioned_at=db_competitor.last_mentioned_at,
        is_active=db_competitor.is_active,
        created_at=db_competitor.created_at
    )


@router.delete("/competitors/{competitor_id}")
async def delete_competitor(
    competitor_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete (deactivate) a competitor."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_competitor = db.query(Competitor).filter(
        Competitor.id == competitor_id,
        Competitor.user_id == user_id
    ).first()
    
    if not db_competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    
    db_competitor.is_active = False
    db.commit()
    
    return {"success": True, "message": "Competitor deleted"}


# ==================== Check & Report Endpoints ====================

@router.post("/check-now", response_model=CheckNowResponse)
async def run_check_now(
    request: Request,
    db: Session = Depends(get_db)
):
    """Run a full growth check now."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    results = await advisor.run_full_check(db, user_id)
    
    return CheckNowResponse(
        success=True,
        google_seo_count=len(results.get("google_seo", [])),
        chatgpt_count=len(results.get("chatgpt", [])),
        deepseek_count=len(results.get("deepseek", [])),
        perplexity_count=len(results.get("perplexity", [])),
        recommendations_count=len(results.get("recommendations", [])),
        report_id=results.get("report", {}).get("id") if results.get("report") else None
    )


@router.get("/report", response_model=Optional[ReportResponse])
async def get_latest_report(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the latest daily growth report."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    report = await advisor.get_latest_report(db, user_id)
    
    if not report:
        return None
    
    return ReportResponse(**report)


@router.get("/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db)
):
    """Get growth recommendations."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    recommendations = await advisor.get_recommendations(db, user_id, status, limit)
    
    return [RecommendationResponse(**r) for r in recommendations]


@router.put("/recommendations/{recommendation_id}/status")
async def update_recommendation_status(
    recommendation_id: int,
    status: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update the status of a recommendation."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if status not in ["pending", "in_progress", "completed", "dismissed"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    advisor = get_growth_advisor()
    success = await advisor.update_recommendation_status(db, user_id, recommendation_id, status)
    
    if not success:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    return {"success": True, "message": f"Status updated to {status}"}


@router.get("/metrics/seo")
async def get_seo_metrics(
    request: Request,
    keyword_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get SEO metrics for keywords."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    metrics = await advisor.get_keyword_metrics(db, user_id, keyword_id)
    
    return metrics


@router.get("/metrics/ai-visibility")
async def get_ai_visibility_metrics(
    request: Request,
    keyword_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get AI visibility metrics."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    metrics = await advisor.get_ai_visibility_metrics(db, user_id, keyword_id)
    
    return metrics


@router.get("/trends/visibility")
async def get_visibility_trends(
    request: Request,
    days: int = Query(default=30, le=90),
    db: Session = Depends(get_db)
):
    """Get AI visibility trends for charting."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    trends = await advisor.get_visibility_trends(db, user_id, days)
    
    return trends


@router.get("/trends/seo")
async def get_seo_trends(
    request: Request,
    days: int = Query(default=30, le=90),
    db: Session = Depends(get_db)
):
    """Get SEO trends for charting."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    trends = await advisor.get_seo_trends(db, user_id, days)
    
    return trends


@router.get("/trends/competitors")
async def get_competitor_trends(
    request: Request,
    days: int = Query(default=30, le=90),
    db: Session = Depends(get_db)
):
    """Get competitor mention trends."""
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    advisor = get_growth_advisor()
    trends = await advisor.get_competitor_trends(db, user_id, days)
    
    return trends


@router.get("/status")
async def get_growth_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get growth advisor status and API configuration."""
    from app.services.google_seo_monitor import get_google_seo_monitor
    from app.services.chatgpt_visibility_monitor import get_chatgpt_monitor
    from app.services.deepseek_visibility_monitor import get_deepseek_monitor
    from app.services.perplexity_visibility_monitor import get_perplexity_monitor
    
    user_id = require_sms_verified(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    google_seo = get_google_seo_monitor()
    chatgpt = get_chatgpt_monitor()
    deepseek = get_deepseek_monitor()
    perplexity = get_perplexity_monitor()
    
    # Count user's data
    keyword_count = db.query(SEOKeyword).filter(SEOKeyword.user_id == user_id).count()
    competitor_count = db.query(Competitor).filter(
        Competitor.user_id == user_id,
        Competitor.is_active == True
    ).count()
    
    return {
        "google_seo": {
            "mock_mode": google_seo.is_mock_mode(),
            "configured": bool(google_seo.credentials if hasattr(google_seo, 'credentials') else False)
        },
        "chatgpt": {
            "mock_mode": chatgpt.is_mock_mode(),
            "configured": bool(chatgpt.api_key if hasattr(chatgpt, 'api_key') else False)
        },
        "deepseek": {
            "mock_mode": deepseek.is_mock_mode(),
            "configured": bool(deepseek.api_key if hasattr(deepseek, 'api_key') else False)
        },
        "perplexity": {
            "mock_mode": perplexity.is_mock_mode(),
            "configured": bool(perplexity.api_key if hasattr(perplexity, 'api_key') else False)
        },
        "user_data": {
            "keywords_tracked": keyword_count,
            "competitors_tracked": competitor_count
        },
        "target_domains": [
            "www.et-expo.com",
            "www.etexpous.com"
        ]
    }