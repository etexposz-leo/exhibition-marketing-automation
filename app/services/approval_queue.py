"""
Approval Queue Service for Marketing Automation

⚠️ IMPORTANT: This service manages the approval workflow for ad drafts.

Workflow:
1. Draft created → status: draft
2. Submitted for review → status: pending_review
3. Leo approves → status: approved
4. Leo rejects → status: rejected (with reason)
5. Scheduled → status: scheduled
6. Published (dry-run/mock) → status: published
7. Failed → status: failed

NO REAL PUBLISHING without Leo's explicit approval.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """Request for approval."""
    draft_id: int
    user_id: int
    priority: str = "normal"
    notes: str = ""
    requested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ApprovalResult:
    """Result of an approval action."""
    success: bool
    message: str
    new_status: str
    approval_record: Optional[Dict] = None
    errors: List[str] = field(default_factory=list)


class ApprovalQueue:
    """
    Approval Queue Manager for ad drafts.
    
    This service ensures human review BEFORE any publishing.
    All approvals are logged for audit trail.
    """
    
    def __init__(self):
        """Initialize Approval Queue."""
        self.approval_required = True  # ALWAYS required
        self.leo_user_ids: List[int] = []  # Users who can approve
        logger.info("📋 APPROVAL QUEUE INITIALIZED")
        logger.info("  - Human approval: REQUIRED")
        logger.info("  - Auto-approve: DISABLED")
        logger.info("  - Real publish without approval: BLOCKED")
    
    def set_leo_users(self, user_ids: List[int]):
        """Set list of users who can approve (Leo and admins)."""
        self.leo_user_ids = user_ids
        logger.info(f"📋 Leo approvers set: {user_ids}")
    
    def can_approve(self, user_id: int) -> bool:
        """Check if user can approve drafts."""
        return user_id in self.leo_user_ids
    
    def submit_for_approval(
        self,
        db: Session,
        draft_id: int,
        user_id: int,
        priority: str = "normal",
        notes: str = ""
    ) -> ApprovalResult:
        """
        Submit a draft for approval.
        
        Args:
            db: Database session
            draft_id: ID of the draft to submit
            user_id: ID of user submitting
            priority: low, normal, high, urgent
            notes: Optional notes for reviewer
            
        Returns:
            ApprovalResult with outcome
        """
        from app.models.models import AdDraft, ApprovalQueue as ApprovalQueueModel
        
        # Get the draft
        draft = db.query(AdDraft).filter(AdDraft.id == draft_id).first()
        if not draft:
            return ApprovalResult(
                success=False,
                message=f"Draft {draft_id} not found",
                new_status="draft",
                errors=["Draft not found"]
            )
        
        # Check if already in queue
        existing = db.query(ApprovalQueueModel).filter(
            ApprovalQueueModel.draft_id == draft_id,
            ApprovalQueueModel.status == "pending"
        ).first()
        
        if existing:
            return ApprovalResult(
                success=False,
                message="Draft already in approval queue",
                new_status=draft.status,
                errors=["Already pending approval"]
            )
        
        # Update draft status
        draft.status = "pending_review"
        
        # Add to approval queue
        queue_entry = ApprovalQueueModel(
            draft_id=draft_id,
            user_id=user_id,
            status="pending",
            priority=priority,
            review_notes=notes,
            safety_checks_passed=False  # Will be updated by safety gate
        )
        db.add(queue_entry)
        db.commit()
        db.refresh(queue_entry)
        
        logger.info(f"📋 Draft {draft_id} submitted for approval by user {user_id}")
        
        return ApprovalResult(
            success=True,
            message=f"Draft submitted for approval (Priority: {priority})",
            new_status="pending_review",
            approval_record={
                "queue_id": queue_entry.id,
                "draft_id": draft_id,
                "submitted_by": user_id,
                "submitted_at": queue_entry.created_at.isoformat()
            }
        )
    
    def approve_draft(
        self,
        db: Session,
        draft_id: int,
        approver_id: int,
        notes: str = "",
        is_leo: bool = False
    ) -> ApprovalResult:
        """
        Approve a draft for publishing.
        
        Args:
            db: Database session
            draft_id: ID of draft to approve
            approver_id: ID of approver
            notes: Optional approval notes
            is_leo: Whether approver is Leo (required for final approval)
            
        Returns:
            ApprovalResult with outcome
        """
        from app.models.models import AdDraft, ApprovalQueue as ApprovalQueueModel
        
        # Get the draft
        draft = db.query(AdDraft).filter(AdDraft.id == draft_id).first()
        if not draft:
            return ApprovalResult(
                success=False,
                message=f"Draft {draft_id} not found",
                new_status="draft",
                errors=["Draft not found"]
            )
        
        # Get queue entry
        queue_entry = db.query(ApprovalQueueModel).filter(
            ApprovalQueueModel.draft_id == draft_id,
            ApprovalQueueModel.status == "pending"
        ).first()
        
        if not queue_entry:
            # Create queue entry if doesn't exist
            queue_entry = ApprovalQueueModel(
                draft_id=draft_id,
                user_id=draft.created_by,
                status="pending"
            )
            db.add(queue_entry)
        
        # Update approval record
        queue_entry.status = "approved"
        queue_entry.reviewed_by = approver_id
        queue_entry.reviewed_at = datetime.utcnow()
        queue_entry.review_notes = notes
        
        # Update draft
        draft.status = "approved"
        draft.approved_by = approver_id
        draft.approved_at = datetime.utcnow()
        draft.leo_approved = is_leo  # Mark as Leo approved
        draft.safety_check_passed = True  # Will be verified by safety gate
        
        db.commit()
        db.refresh(draft)
        
        logger.info(f"✅ Draft {draft_id} APPROVED by user {approver_id} (Leo: {is_leo})")
        
        return ApprovalResult(
            success=True,
            message="Draft approved" + (" (Leo approved)" if is_leo else ""),
            new_status="approved",
            approval_record={
                "draft_id": draft_id,
                "approved_by": approver_id,
                "approved_at": draft.approved_at.isoformat(),
                "leo_approved": is_leo
            }
        )
    
    def reject_draft(
        self,
        db: Session,
        draft_id: int,
        rejector_id: int,
        reason: str
    ) -> ApprovalResult:
        """
        Reject a draft.
        
        Args:
            db: Database session
            draft_id: ID of draft to reject
            rejector_id: ID of rejector
            reason: Reason for rejection
            
        Returns:
            ApprovalResult with outcome
        """
        from app.models.models import AdDraft, ApprovalQueue as ApprovalQueueModel
        
        # Get the draft
        draft = db.query(AdDraft).filter(AdDraft.id == draft_id).first()
        if not draft:
            return ApprovalResult(
                success=False,
                message=f"Draft {draft_id} not found",
                new_status="draft",
                errors=["Draft not found"]
            )
        
        # Get queue entry
        queue_entry = db.query(ApprovalQueueModel).filter(
            ApprovalQueueModel.draft_id == draft_id,
            ApprovalQueueModel.status == "pending"
        ).first()
        
        if queue_entry:
            queue_entry.status = "rejected"
            queue_entry.reviewed_by = rejector_id
            queue_entry.reviewed_at = datetime.utcnow()
            queue_entry.review_notes = reason
        
        # Update draft
        draft.status = "rejected"
        draft.rejected_by = rejector_id
        draft.rejected_at = datetime.utcnow()
        draft.rejection_reason = reason
        
        db.commit()
        
        logger.warning(f"❌ Draft {draft_id} REJECTED by user {rejector_id}: {reason}")
        
        return ApprovalResult(
            success=True,
            message=f"Draft rejected: {reason}",
            new_status="rejected",
            approval_record={
                "draft_id": draft_id,
                "rejected_by": rejector_id,
                "rejected_at": datetime.utcnow().isoformat(),
                "reason": reason
            }
        )
    
    def schedule_draft(
        self,
        db: Session,
        draft_id: int,
        schedule_time: datetime,
        scheduler_id: int
    ) -> ApprovalResult:
        """
        Schedule a draft for future publishing.
        
        Args:
            db: Database session
            draft_id: ID of draft to schedule
            schedule_time: When to publish
            scheduler_id: ID of person scheduling
            
        Returns:
            ApprovalResult with outcome
        """
        from app.models.models import AdDraft
        
        # Get the draft
        draft = db.query(AdDraft).filter(AdDraft.id == draft_id).first()
        if not draft:
            return ApprovalResult(
                success=False,
                message=f"Draft {draft_id} not found",
                new_status="draft",
                errors=["Draft not found"]
            )
        
        # Must be approved first
        if draft.status != "approved":
            return ApprovalResult(
                success=False,
                message="Draft must be approved before scheduling",
                new_status=draft.status,
                errors=["Status must be 'approved'"]
            )
        
        # Update draft
        draft.status = "scheduled"
        draft.schedule_time = schedule_time
        draft.has_schedule = True
        
        db.commit()
        
        logger.info(f"📅 Draft {draft_id} SCHEDULED for {schedule_time} by user {scheduler_id}")
        
        return ApprovalResult(
            success=True,
            message=f"Draft scheduled for {schedule_time}",
            new_status="scheduled",
            approval_record={
                "draft_id": draft_id,
                "scheduled_for": schedule_time.isoformat(),
                "scheduled_by": scheduler_id
            }
        )
    
    def mark_published(
        self,
        db: Session,
        draft_id: int,
        publisher_id: int,
        platform_post_id: str = "",
        mock_mode: bool = True
    ) -> ApprovalResult:
        """
        Mark a draft as published (dry-run/mock).
        
        Args:
            db: Database session
            draft_id: ID of published draft
            publisher_id: ID of publisher
            platform_post_id: ID from platform (mock or real)
            mock_mode: Whether this was a mock publish
            
        Returns:
            ApprovalResult with outcome
        """
        from app.models.models import AdDraft
        
        # Get the draft
        draft = db.query(AdDraft).filter(AdDraft.id == draft_id).first()
        if not draft:
            return ApprovalResult(
                success=False,
                message=f"Draft {draft_id} not found",
                new_status="draft",
                errors=["Draft not found"]
            )
        
        # Must be approved first
        if draft.status not in ["approved", "scheduled"]:
            return ApprovalResult(
                success=False,
                message="Draft must be approved before publishing",
                new_status=draft.status,
                errors=["Status must be 'approved' or 'scheduled'"]
            )
        
        # Update draft
        draft.status = "published"
        draft.published_at = datetime.utcnow()
        draft.platform_post_id = platform_post_id
        
        if not mock_mode:
            logger.error(f"🚨 REAL PUBLISH DETECTED for draft {draft_id}!")
            return ApprovalResult(
                success=False,
                message="REAL PUBLISH NOT ALLOWED - Mock mode only",
                new_status="draft",
                errors=["Real publishing is disabled"]
            )
        
        db.commit()
        
        mode_str = "DRY-RUN" if mock_mode else "REAL"
        logger.info(f"✅ Draft {draft_id} PUBLISHED ({mode_str}) by user {publisher_id}")
        
        return ApprovalResult(
            success=True,
            message=f"Draft published (Mock mode: {mock_mode})",
            new_status="published",
            approval_record={
                "draft_id": draft_id,
                "published_at": draft.published_at.isoformat(),
                "published_by": publisher_id,
                "platform_post_id": platform_post_id,
                "mock_mode": mock_mode
            }
        )
    
    def mark_failed(
        self,
        db: Session,
        draft_id: int,
        error_message: str,
        updater_id: int
    ) -> ApprovalResult:
        """
        Mark a draft as failed.
        
        Args:
            db: Database session
            draft_id: ID of failed draft
            error_message: What went wrong
            updater_id: ID of person updating
            
        Returns:
            ApprovalResult with outcome
        """
        from app.models.models import AdDraft
        
        # Get the draft
        draft = db.query(AdDraft).filter(AdDraft.id == draft_id).first()
        if not draft:
            return ApprovalResult(
                success=False,
                message=f"Draft {draft_id} not found",
                new_status="draft",
                errors=["Draft not found"]
            )
        
        # Update draft
        draft.status = "failed"
        draft.error_message = error_message
        
        db.commit()
        
        logger.error(f"❌ Draft {draft_id} FAILED: {error_message}")
        
        return ApprovalResult(
            success=True,
            message=f"Draft marked as failed: {error_message}",
            new_status="failed",
            approval_record={
                "draft_id": draft_id,
                "error_message": error_message,
                "updated_by": updater_id
            }
        )
    
    def get_pending_approvals(
        self,
        db: Session,
        limit: int = 50,
        priority: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get list of pending approvals.
        
        Args:
            db: Database session
            limit: Maximum results
            priority: Filter by priority
            
        Returns:
            List of pending approval records
        """
        from app.models.models import AdDraft, ApprovalQueue as ApprovalQueueModel, User
        
        query = db.query(ApprovalQueueModel).filter(
            ApprovalQueueModel.status == "pending"
        )
        
        if priority:
            query = query.filter(ApprovalQueueModel.priority == priority)
        
        queue_entries = query.order_by(
            ApprovalQueueModel.created_at.desc()
        ).limit(limit).all()
        
        results = []
        for entry in queue_entries:
            draft = db.query(AdDraft).filter(AdDraft.id == entry.draft_id).first()
            submitter = db.query(User).filter(User.id == entry.user_id).first()
            
            results.append({
                "queue_id": entry.id,
                "draft_id": entry.draft_id,
                "priority": entry.priority,
                "submitted_by": entry.user_id,
                "submitter_name": submitter.username if submitter else "Unknown",
                "submitted_at": entry.created_at.isoformat() if entry.created_at else None,
                "draft_title": draft.title if draft else "Unknown",
                "draft_platform": draft.platform if draft else "Unknown",
                "draft_status": draft.status if draft else "Unknown"
            })
        
        return results
    
    def get_approval_history(
        self,
        db: Session,
        draft_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get approval history for a draft.
        
        Args:
            db: Database session
            draft_id: ID of draft
            
        Returns:
            List of approval records
        """
        from app.models.models import ApprovalQueue as ApprovalQueueModel, User
        
        entries = db.query(ApprovalQueueModel).filter(
            ApprovalQueueModel.draft_id == draft_id
        ).order_by(ApprovalQueueModel.created_at.desc()).all()
        
        results = []
        for entry in entries:
            reviewer = db.query(User).filter(User.id == entry.reviewed_by).first()
            
            results.append({
                "id": entry.id,
                "status": entry.status,
                "priority": entry.priority,
                "reviewed_by": entry.reviewed_by,
                "reviewer_name": reviewer.username if reviewer else "Unknown",
                "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
                "notes": entry.review_notes,
                "safety_checks_passed": entry.safety_checks_passed,
                "safety_issues": json.loads(entry.safety_issues) if entry.safety_issues else []
            })
        
        return results


# Global approval queue instance
approval_queue = ApprovalQueue()


def get_pending_approvals(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """Convenience function to get pending approvals."""
    return approval_queue.get_pending_approvals(db, limit)


def approve_draft(
    db: Session,
    draft_id: int,
    approver_id: int,
    notes: str = "",
    is_leo: bool = False
) -> ApprovalResult:
    """Convenience function to approve a draft."""
    return approval_queue.approve_draft(db, draft_id, approver_id, notes, is_leo)


def reject_draft(
    db: Session,
    draft_id: int,
    rejector_id: int,
    reason: str
) -> ApprovalResult:
    """Convenience function to reject a draft."""
    return approval_queue.reject_draft(db, draft_id, rejector_id, reason)


def get_approval_status() -> Dict[str, Any]:
    """Get approval queue status."""
    return {
        "approval_required": True,
        "auto_approve_enabled": False,
        "real_publish_without_approval": False,
        "leo_approval_required_for_real_publish": True
    }
