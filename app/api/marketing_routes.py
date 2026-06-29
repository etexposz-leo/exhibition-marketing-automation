"""
Marketing API Routes

⚠️ IMPORTANT: These routes manage ad drafts, approval queue, and publishing.

Safety measures:
- All drafts start in 'draft' status
- Must go through approval queue
- Safety gate must pass before any publish
- Only mock/dry-run publishing enabled
- NO real API calls
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_db as db_dependency
from app.models.models import User, AdDraft, ApprovalQueue, PublishLog
from app.services.mock_publishers import (
    get_mock_publisher,
    list_mock_publishers,
    SAFETY_STATUS
)
from app.services.safety_gate import run_safety_check, get_safety_status
from app.services.approval_queue import (
    approval_queue,
    get_pending_approvals,
    approve_draft as queue_approve_draft,
    reject_draft as queue_reject_draft
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing", tags=["marketing"])


def get_current_user_simple(request: Request, db: Session = Depends(db_dependency)) -> dict:
    """Get current user from session."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {"id": user.id, "email": user.email, "username": user.username, "company_name": user.company_name}


# ==================== Draft Management ====================


@router.get("/drafts")
async def list_drafts(
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple),
    status: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    limit: int = Query(50, le=100)
):
    """
    List all drafts for current user.
    
    Args:
        status: Filter by status (draft, pending_review, approved, etc.)
        platform: Filter by platform
        limit: Max results
    """
    query = db.query(AdDraft).filter(AdDraft.user_id == current_user.id)
    
    if status:
        query = query.filter(AdDraft.status == status)
    if platform:
        query = query.filter(AdDraft.platform == platform)
    
    drafts = query.order_by(AdDraft.created_at.desc()).limit(limit).all()
    
    return {
        "success": True,
        "count": len(drafts),
        "drafts": [
            {
                "id": d.id,
                "platform": d.platform,
                "campaign_type": d.campaign_type,
                "title": d.title,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "safety_check_passed": d.safety_check_passed,
                "leo_approved": d.leo_approved
            }
            for d in drafts
        ]
    }


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: int,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple)
):
    """Get a single draft by ID."""
    draft = db.query(AdDraft).filter(
        AdDraft.id == draft_id,
        AdDraft.user_id == current_user.id
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    return {
        "success": True,
        "draft": {
            "id": draft.id,
            "platform": draft.platform,
            "campaign_type": draft.campaign_type,
            "title": draft.title,
            "body": draft.body,
            "cta": draft.cta,
            "image_url": draft.image_url,
            "target_keywords": json.loads(draft.target_keywords) if draft.target_keywords else [],
            "target_audience": json.loads(draft.target_audience) if draft.target_audience else {},
            "target_locations": json.loads(draft.target_locations) if draft.target_locations else [],
            "target_age_range": draft.target_age_range,
            "landing_page": draft.landing_page,
            "suggested_budget": draft.suggested_budget,
            "daily_budget": draft.daily_budget,
            "schedule_time": draft.schedule_time.isoformat() if draft.schedule_time else None,
            "start_date": draft.start_date.isoformat() if draft.start_date else None,
            "end_date": draft.end_date.isoformat() if draft.end_date else None,
            "status": draft.status,
            "created_by": draft.created_by,
            "approved_by": draft.approved_by,
            "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
            "published_at": draft.published_at.isoformat() if draft.published_at else None,
            "error_message": draft.error_message,
            "safety_check_passed": draft.safety_check_passed,
            "safety_warnings": json.loads(draft.safety_warnings) if draft.safety_warnings else [],
            "leo_approved": draft.leo_approved,
            "seo_keywords": json.loads(draft.seo_keywords) if draft.seo_keywords else [],
            "seo_meta_description": draft.seo_meta_description,
            "email_subject": draft.email_subject,
            "version": draft.version,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "updated_at": draft.updated_at.isoformat() if draft.updated_at else None
        }
    }


@router.post("/drafts")
async def create_draft(
    draft_data: Dict[str, Any],
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple)
):
    """
    Create a new ad draft.
    
    Default status: draft (requires approval to publish)
    """
    # Validate platform
    valid_platforms = ["google_ads", "linkedin", "facebook", "google_business", "email", "seo_article"]
    platform = draft_data.get("platform", "")
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform. Must be one of: {valid_platforms}"
        )
    
    # Create draft
    draft = AdDraft(
        user_id=current_user.id,
        platform=platform,
        campaign_type=draft_data.get("campaign_type", "post"),
        title=draft_data.get("title"),
        body=draft_data.get("body"),
        cta=draft_data.get("cta"),
        image_url=draft_data.get("image_url"),
        target_keywords=json.dumps(draft_data.get("target_keywords", [])),
        target_audience=json.dumps(draft_data.get("target_audience", {})),
        target_locations=json.dumps(draft_data.get("target_locations", [])),
        target_age_range=draft_data.get("target_age_range"),
        landing_page=draft_data.get("landing_page"),
        suggested_budget=draft_data.get("suggested_budget", 0),
        daily_budget=draft_data.get("daily_budget", 0),
        start_date=draft_data.get("start_date"),
        end_date=draft_data.get("end_date"),
        status="draft",  # Always start as draft
        created_by=current_user.id,
        seo_keywords=json.dumps(draft_data.get("seo_keywords", [])),
        seo_meta_description=draft_data.get("seo_meta_description"),
        email_subject=draft_data.get("email_subject"),
        email_recipients=json.dumps(draft_data.get("email_recipients", []))
    )
    
    db.add(draft)
    db.commit()
    db.refresh(draft)
    
    logger.info(f"📝 Draft {draft.id} created by user {current_user.id}")
    
    return {
        "success": True,
        "message": "Draft created (status: draft - requires approval)",
        "draft_id": draft.id
    }


@router.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: int,
    draft_data: Dict[str, Any],
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple)
):
    """Update an existing draft."""
    draft = db.query(AdDraft).filter(
        AdDraft.id == draft_id,
        AdDraft.user_id == current_user.id
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    # Can only update drafts that are not yet published
    if draft.status in ["published", "scheduled"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot update draft that is published or scheduled"
        )
    
    # Update fields
    for field in ["title", "body", "cta", "image_url", "target_age_range",
                  "landing_page", "suggested_budget", "daily_budget", "seo_meta_description",
                  "email_subject"]:
        if field in draft_data:
            setattr(draft, field, draft_data[field])
    
    # Update JSON fields
    if "target_keywords" in draft_data:
        draft.target_keywords = json.dumps(draft_data["target_keywords"])
    if "target_audience" in draft_data:
        draft.target_audience = json.dumps(draft_data["target_audience"])
    if "target_locations" in draft_data:
        draft.target_locations = json.dumps(draft_data["target_locations"])
    if "seo_keywords" in draft_data:
        draft.seo_keywords = json.dumps(draft_data["seo_keywords"])
    if "email_recipients" in draft_data:
        draft.email_recipients = json.dumps(draft_data["email_recipients"])
    
    # If updating content, reset to draft status
    if draft.status not in ["draft"]:
        draft.status = "draft"
        draft.leo_approved = False
        draft.approved_by = None
        draft.approved_at = None
    
    draft.version += 1
    db.commit()
    
    logger.info(f"📝 Draft {draft_id} updated by user {current_user.id}")
    
    return {
        "success": True,
        "message": "Draft updated",
        "draft_id": draft_id,
        "status": draft.status
    }


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: int,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple)
):
    """Delete a draft."""
    draft = db.query(AdDraft).filter(
        AdDraft.id == draft_id,
        AdDraft.user_id == current_user.id
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    # Cannot delete published drafts
    if draft.status == "published":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete published drafts"
        )
    
    db.delete(draft)
    db.commit()
    
    logger.info(f"🗑️ Draft {draft_id} deleted by user {current_user.id}")
    
    return {"success": True, "message": "Draft deleted"}


# ==================== Approval Queue ====================


@router.get("/approvals")
async def list_approvals(
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple),
    status: Optional[str] = Query(None)
):
    """List approval queue entries."""
    approvals = approval_queue.get_pending_approvals(db, limit=100, priority=status)
    
    return {
        "success": True,
        "count": len(approvals),
        "approvals": approvals
    }


@router.post("/drafts/{draft_id}/submit")
async def submit_for_approval(
    draft_id: int,
    request: Request,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple),
    priority: str = Query("normal"),
    notes: str = Query("")
):
    """
    Submit a draft for approval.
    
    This will:
    1. Run safety gate check
    2. Add to approval queue
    3. Change status to pending_review
    """
    # Get draft
    draft = db.query(AdDraft).filter(
        AdDraft.id == draft_id,
        AdDraft.user_id == current_user.id
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    # Run safety check
    safety_result = run_safety_check(
        content={
            "platform": draft.platform,
            "title": draft.title,
            "body": draft.body,
            "cta": draft.cta,
            "landing_page": draft.landing_page,
            "suggested_budget": draft.suggested_budget,
            "schedule_time": draft.schedule_time,
            "leo_approved": False  # Not yet approved
        },
        is_mock_mode=True  # Always mock mode
    )
    
    # Update safety fields
    draft.safety_check_passed = safety_result.all_passed
    draft.safety_warnings = json.dumps(safety_result.warnings)
    
    # Check for API key leaks (critical)
    api_key_check = next(
        (c for c in safety_result.checks if c.check_name == "api_key_leak"),
        None
    )
    if api_key_check and not api_key_check.passed:
        raise HTTPException(
            status_code=400,
            detail=f"Safety check failed: {api_key_check.message}"
        )
    
    # Submit for approval
    result = approval_queue.submit_for_approval(
        db=db,
        draft_id=draft_id,
        user_id=current_user.id,
        priority=priority,
        notes=notes
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    # Log the submission
    log_entry = PublishLog(
        draft_id=draft_id,
        user_id=current_user.id,
        action="submit_for_approval",
        status="success",
        platform=draft.platform,
        mock_mode=True,
        request_data=json.dumps({"priority": priority, "notes": notes}),
        response_data=json.dumps(safety_result.__dict__),
        safety_issues=json.dumps(safety_result.warnings)
    )
    db.add(log_entry)
    db.commit()
    
    return {
        "success": True,
        "message": result.message,
        "safety_check_passed": safety_result.all_passed,
        "safety_warnings": safety_result.warnings,
        "safety_errors": safety_result.errors
    }


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: int,
    request: Request,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple),
    notes: str = Query(""),
    is_leo: bool = Query(False)
):
    """
    Approve a draft for publishing.
    
    ⚠️ is_leo flag: Must be True only when Leo explicitly approves.
    """
    # Verify user can approve (simplified - in production, check user role)
    # For now, allow any authenticated user but log if not Leo
    
    result = queue_approve_draft(
        db=db,
        draft_id=draft_id,
        approver_id=current_user.id,
        notes=notes,
        is_leo=is_leo  # Should only be True when Leo explicitly approves
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    # Log approval
    log_entry = PublishLog(
        draft_id=draft_id,
        user_id=current_user.id,
        action="approve",
        status="success",
        response_data=json.dumps({
            "approved_by": current_user.id,
            "is_leo": is_leo,
            "notes": notes
        })
    )
    db.add(log_entry)
    db.commit()
    
    logger.info(f"✅ Draft {draft_id} approved by user {current_user.id} (Leo: {is_leo})")
    
    return {
        "success": True,
        "message": result.message,
        "is_leo_approved": is_leo
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: int,
    request: Request,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple),
    reason: str = Query(...)
):
    """Reject a draft with reason."""
    result = queue_reject_draft(
        db=db,
        draft_id=draft_id,
        rejector_id=current_user.id,
        reason=reason
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    # Log rejection
    log_entry = PublishLog(
        draft_id=draft_id,
        user_id=current_user.id,
        action="reject",
        status="success",
        response_data=json.dumps({
            "rejected_by": current_user.id,
            "reason": reason
        })
    )
    db.add(log_entry)
    db.commit()
    
    logger.warning(f"❌ Draft {draft_id} rejected by user {current_user.id}: {reason}")
    
    return {
        "success": True,
        "message": result.message
    }


# ==================== Mock Publishing ====================


@router.post("/drafts/{draft_id}/dry-run")
async def run_dry_run(
    draft_id: int,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple)
):
    """
    Run a dry-run of the publish without actually publishing.
    
    This is the SAFE way to test before approval.
    """
    draft = db.query(AdDraft).filter(
        AdDraft.id == draft_id,
        AdDraft.user_id == current_user.id
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    # Get mock publisher
    try:
        publisher = get_mock_publisher(draft.platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Prepare content
    content = {
        "title": draft.title,
        "body": draft.body,
        "cta": draft.cta,
        "platform": draft.platform,
        "landing_page": draft.landing_page,
        "suggested_budget": draft.suggested_budget,
        "target_keywords": json.loads(draft.target_keywords) if draft.target_keywords else [],
        "email_subject": draft.email_subject,
        "email_recipients": json.loads(draft.email_recipients) if draft.email_recipients else [],
        "seo_keywords": json.loads(draft.seo_keywords) if draft.seo_keywords else [],
        "seo_meta_description": draft.seo_meta_description
    }
    
    # Run dry-run
    result = await publisher.dry_run(content)
    
    # Log the dry-run
    log_entry = PublishLog(
        draft_id=draft_id,
        user_id=current_user.id,
        action="dry_run",
        status="success" if result.success else "failed",
        platform=draft.platform,
        mock_mode=True,
        request_data=json.dumps(content),
        response_data=json.dumps(result.response_data),
        error_message=result.error_message
    )
    db.add(log_entry)
    db.commit()
    
    logger.info(f"🔍 Dry-run completed for draft {draft_id}")
    
    return {
        "success": result.success,
        "mock_mode": True,
        "message": result.message,
        "warnings": result.warnings,
        "platform_post_id": result.platform_post_id,
        "note": "DRY-RUN ONLY - No real publish occurred"
    }


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(
    draft_id: int,
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple)
):
    """
    Publish a draft (DRY-RUN ONLY).
    
    ⚠️ This ONLY runs in mock/dry-run mode.
    NO real publishing occurs.
    
    Requirements:
    1. Draft must be in 'approved' status
    2. Leo must have approved (leo_approved = True)
    3. Safety gate must pass
    """
    draft = db.query(AdDraft).filter(
        AdDraft.id == draft_id,
        AdDraft.user_id == current_user.id
    ).first()
    
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    # Check status
    if draft.status not in ["approved", "scheduled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot publish: draft status is '{draft.status}', must be 'approved'"
        )
    
    # Check Leo approval
    if not draft.leo_approved:
        raise HTTPException(
            status_code=403,
            detail="Cannot publish: Leo approval required"
        )
    
    # Run safety check
    safety_result = run_safety_check(
        content={
            "platform": draft.platform,
            "title": draft.title,
            "body": draft.body,
            "cta": draft.cta,
            "landing_page": draft.landing_page,
            "suggested_budget": draft.suggested_budget,
            "schedule_time": draft.schedule_time,
            "leo_approved": draft.leo_approved
        },
        is_mock_mode=True  # Always mock mode
    )
    
    if not safety_result.all_passed:
        raise HTTPException(
            status_code=400,
            detail=f"Safety check failed: {safety_result.errors}"
        )
    
    # Get mock publisher
    try:
        publisher = get_mock_publisher(draft.platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Prepare content
    content = {
        "title": draft.title,
        "body": draft.body,
        "cta": draft.cta,
        "platform": draft.platform,
        "landing_page": draft.landing_page,
        "suggested_budget": draft.suggested_budget,
        "target_keywords": json.loads(draft.target_keywords) if draft.target_keywords else [],
        "email_subject": draft.email_subject,
        "email_recipients": json.loads(draft.email_recipients) if draft.email_recipients else [],
        "seo_keywords": json.loads(draft.seo_keywords) if draft.seo_keywords else [],
        "seo_meta_description": draft.seo_meta_description
    }
    
    # Run mock publish
    result = await publisher.publish(content)
    
    # Update draft status
    draft.status = "published"
    draft.published_at = datetime.utcnow()
    draft.platform_post_id = result.platform_post_id
    
    # Log the publish
    log_entry = PublishLog(
        draft_id=draft_id,
        user_id=current_user.id,
        action="publish",
        status="success",
        platform=draft.platform,
        mock_mode=True,  # ALWAYS True
        request_data=json.dumps(content),
        response_data=json.dumps(result.response_data),
        cost_cents=result.cost_cents,  # Always 0 in mock mode
        impressions=result.impressions,  # Always 0 in mock mode
        clicks=result.clicks  # Always 0 in mock mode
    )
    db.add(log_entry)
    db.commit()
    
    logger.warning(
        f"🔄 DRY-RUN PUBLISH: Draft {draft_id} (MOCK MODE - No real publish)"
    )
    
    return {
        "success": True,
        "mock_mode": True,
        "message": "DRY-RUN PUBLISH SUCCESSFUL (No real publish occurred)",
        "platform_post_id": result.platform_post_id,
        "warnings": result.warnings,
        "cost": 0,  # No cost in mock mode
        "note": "⚠️ THIS WAS A DRY-RUN. No real ads were published."
    }


# ==================== Safety & Status ====================


@router.get("/safety/status")
async def get_marketing_safety_status():
    """Get safety status for marketing module."""
    return {
        "safety_gate_enabled": True,
        "safety_checks": [
            "leo_approval",
            "platform",
            "landing_page",
            "budget",
            "sensitive_content",
            "exaggeration",
            "api_key_leak",
            "mock_mode"
        ],
        "publishers_status": list_mock_publishers(),
        "approval_required": True,
        "human_approval_required": True,
        "auto_publish_enabled": False,
        "mock_mode_only": True,
        "real_api_enabled": False,
        **SAFETY_STATUS
    }


@router.get("/publishers")
async def get_publishers():
    """Get list of available publishers (all mock/disabled)."""
    return {
        "success": True,
        "publishers": list_mock_publishers(),
        "note": "All publishers are in DRY-RUN/MOCK mode. No real publishing available."
    }


@router.get("/logs")
async def get_publish_logs(
    db: Session = Depends(db_dependency),
    current_user: dict = Depends(get_current_user_simple),
    draft_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, le=100)
):
    """Get publish logs for audit trail."""
    query = db.query(PublishLog).filter(PublishLog.user_id == current_user.id)
    
    if draft_id:
        query = query.filter(PublishLog.draft_id == draft_id)
    if action:
        query = query.filter(PublishLog.action == action)
    
    logs = query.order_by(PublishLog.created_at.desc()).limit(limit).all()
    
    return {
        "success": True,
        "count": len(logs),
        "logs": [
            {
                "id": log.id,
                "draft_id": log.draft_id,
                "action": log.action,
                "status": log.status,
                "platform": log.platform,
                "mock_mode": log.mock_mode,
                "cost_cents": log.cost_cents,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }
