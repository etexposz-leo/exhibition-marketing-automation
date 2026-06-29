# Approval Queue Specification

## Overview

The Approval Queue is a critical component of the ET EXPO Marketing Automation Center that ensures all marketing content is reviewed and approved by authorized personnel before publishing.

---

## 🎯 Objectives

1. **Human Oversight**: Every draft requires human review
2. **Safety First**: All safety checks must pass before approval
3. **Audit Trail**: All actions are logged for accountability
4. **Clear Workflow**: Status transitions are well-defined
5. **No Auto-Publish**: Never publish without explicit approval

---

## 📊 Status Definitions

### Draft Statuses

| Status | Description | Can Transition To |
|--------|-------------|-------------------|
| `draft` | Initial creation, not submitted | `pending_review` |
| `pending_review` | Submitted for approval | `approved`, `rejected` |
| `approved` | Approved by reviewer | `scheduled`, `published` |
| `rejected` | Rejected with reason | `draft` (after revision) |
| `scheduled` | Scheduled for future publish | `published` |
| `published` | Successfully published (mock) | (terminal) |
| `failed` | Publish failed | `draft`, `approved` |

### Queue Entry Statuses

| Status | Description |
|--------|-------------|
| `pending` | Awaiting review |
| `approved` | Reviewed and approved |
| `rejected` | Reviewed and rejected |

---

## 🔄 State Machine

```
                    ┌──────────────┐
                    │    DRAFT     │
                    └──────┬───────┘
                           │ submit_for_approval()
                           ▼
                 ┌─────────────────────┐
                 │   PENDING_REVIEW    │
                 └──────────┬──────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
     ┌──────────────┐           ┌──────────────┐
     │   APPROVED   │           │   REJECTED   │
     └──────┬───────┘           └──────┬───────┘
            │                          │
            │                          │ (revise & resubmit)
            ▼                          │
     ┌──────────────┐                   │
     │  SCHEDULED   │                   │
     └──────┬───────┘                   │
            │                          │
            │ schedule_time reached     │
            ▼                          │
     ┌──────────────┐                   │
     │  PUBLISHED   │◄──────────────────┘
     └──────────────┘
```

---

## 👥 Roles & Permissions

### Creator
- Can create drafts
- Can submit drafts for approval
- Can revise rejected drafts
- Cannot approve own drafts (separation of duties)

### Reviewer
- Can view pending approvals
- Can approve or reject drafts
- Can add notes to approvals
- Cannot publish without additional approval

### Leo (Administrator)
- Can do everything reviewers can
- Required for final approval
- `is_leo` flag required for certain actions
- Can bypass certain restrictions (with logging)

---

## 🚨 Safety Requirements

### Pre-Approval Requirements
Before approving a draft, the reviewer MUST verify:

1. [ ] Content is appropriate for the platform
2. [ ] Landing page is correct and functional
3. [ ] No sensitive or prohibited content
4. [ ] No exaggeration or false claims
5. [ ] Budget is appropriate
6. [ ] Targeting is correctly configured
7. [ ] All safety checks passed

### Leo Approval Requirements
For Leo's final approval:

1. [ ] All pre-approval requirements met
2. [ ] Draft has been reviewed personally
3. [ ] Budget is within approved limits
4. [ ] Campaign aligns with marketing strategy
5. [ ] Legal/compliance review (if applicable)

---

## 📝 API Endpoints

### Submit for Approval
```
POST /api/marketing/drafts/{id}/submit
Query: priority=normal|high|urgent
Body: { notes: string }
```

**Response**:
```json
{
  "success": true,
  "message": "Draft submitted for approval",
  "safety_check_passed": true,
  "safety_warnings": ["Budget not set"],
  "safety_errors": []
}
```

### Approve Draft
```
POST /api/marketing/drafts/{id}/approve
Query: notes=string, is_leo=false
```

**Response**:
```json
{
  "success": true,
  "message": "Draft approved",
  "is_leo_approved": false
}
```

### Reject Draft
```
POST /api/marketing/drafts/{id}/reject
Query: reason=string
```

**Response**:
```json
{
  "success": true,
  "message": "Draft rejected: [reason]"
}
```

---

## 📋 Approval Queue UI

### Pending Approvals List
Shows all drafts awaiting approval with:
- Draft title and platform
- Submission time
- Priority level
- Submitter information
- Quick actions (Approve/Reject)

### Approval Detail View
Shows:
- Full draft content
- Safety check results
- Approval history
- Notes from reviewers

### Filters
- By status: pending, approved, rejected
- By platform
- By priority
- By date range
- By submitter

---

## 🔔 Notifications (Future)

Planned notification features:
- [ ] Email when draft needs review
- [ ] Email when draft approved/rejected
- [ ] Slack notification for urgent items
- [ ] Daily digest of pending approvals

---

## 📊 Metrics

The approval queue tracks:
- Average time to approve
- Approval rate by reviewer
- Rejection reasons analysis
- Draft revision cycles
- Platform approval rates

---

## 🧪 Testing

### Unit Tests
- State transitions work correctly
- Validation rules enforced
- Error handling for edge cases

### Integration Tests
- API endpoints respond correctly
- Database state is consistent
- Logs are created properly

### E2E Tests
- Full approval workflow
- Safety gate enforcement
- Audit trail completeness

---

## 📈 SLA (Service Level Agreement)

| Metric | Target |
|--------|--------|
| Time to first review | < 4 hours |
| Time to approve (normal) | < 24 hours |
| Time to approve (urgent) | < 1 hour |
| Queue depth warning | > 10 pending |

---

## 🔒 Audit Requirements

Every action must be logged:
- Who performed the action
- When the action was performed
- What the action was
- Result of the action
- Related draft details

### Log Entry Fields
```python
{
    "id": int,
    "draft_id": int,
    "user_id": int,
    "action": str,  # submit, approve, reject, schedule, publish
    "status": str,   # success, failed
    "platform": str,
    "mock_mode": bool,
    "request_data": dict,
    "response_data": dict,
    "error_message": str,
    "cost_cents": int,
    "created_at": datetime
}
```

---

## 🚨 Escalation

### Normal Priority
1. Submitted → Reviewed by any reviewer
2. Approved → Published (dry-run)

### Urgent Priority
1. Submitted → Escalated to Leo
2. Leo reviews immediately
3. If approved → Published immediately

### Rejection Escalation
1. Draft rejected → Creator notified
2. Creator revises → Resubmits
3. If rejected twice → Flag for review meeting

---

## 📝 Forms

### Approval Form
```
┌─────────────────────────────────────────┐
│ Approve Draft                           │
├─────────────────────────────────────────┤
│ Draft: [Title]                         │
│ Platform: [Platform]                    │
│ Submitted by: [User]                    │
│ Submitted at: [DateTime]                │
│                                         │
│ Notes (optional):                       │
│ ┌─────────────────────────────────────┐ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ☑ I am Leo and I approve this draft    │
│                                         │
│ [Cancel]              [Approve]        │
└─────────────────────────────────────────┘
```

### Rejection Form
```
┌─────────────────────────────────────────┐
│ Reject Draft                           │
├─────────────────────────────────────────┤
│ Draft: [Title]                         │
│ Platform: [Platform]                   │
│                                         │
│ Reason for rejection:                   │
│ ┌─────────────────────────────────────┐ │
│ │ * Required                          │ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ [Cancel]              [Reject Draft]   │
└─────────────────────────────────────────┘
```

---

## 🔄 Revision Workflow

### After Rejection
1. Creator reviews rejection reason
2. Creator revises draft content
3. Draft status resets to `draft`
4. Creator resubmits for approval
5. Cycle repeats

### Version Tracking
- Each draft has a `version` number
- Version increments on each revision
- Full history is maintained
- Can compare versions (future feature)

---

## 📊 Reporting

### Approval Metrics Report
- Total submissions by period
- Approval rate
- Average time to approve
- Top rejection reasons
- Platform breakdown

### Draft Lifecycle Report
- Time in each status
- Revision count per draft
- Approval funnel visualization

---

## 🛠️ Configuration

### Queue Settings
```python
{
    "auto_expire_hours": 72,  # Auto-expire old pending items
    "max_pending": 50,  # Max pending before warning
    "require_leo_for_platforms": ["google_ads"],  # Platforms requiring Leo
    "allow_self_approval": False,  # Cannot approve own drafts
}
```

---

## 📞 Support

For approval queue issues:
- Contact: admin@example.com
- Slack: #marketing-approval

---

## 📝 Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-06-15 | 1.0 | Initial specification |
| - | - | Status definitions |
| - | - | State machine |
| - | - | API endpoints |
| - | - | UI mockups |
