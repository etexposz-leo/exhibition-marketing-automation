# Marketing Automation Safety Guide

## ⚠️ IMPORTANT SAFETY NOTICES

This document outlines the safety measures implemented in the ET EXPO Marketing Automation Center to prevent accidental publishing, unauthorized access, and financial loss.

---

## 🚫 Current Safety Status

| Feature | Status | Description |
|---------|--------|-------------|
| Real API Integration | ❌ DISABLED | All platform APIs are blocked |
| Mock/Dry-Run Mode | ✅ ENABLED | Only simulates publishing |
| Human Approval | ✅ REQUIRED | All drafts need approval |
| Auto-Publish | ❌ DISABLED | No automatic publishing |
| Cost Tracking | ✅ ACTIVE | All costs are $0 in mock mode |
| API Key Detection | ✅ ACTIVE | Blocks credential leaks |

---

## 🔒 Safety Gates

Before any draft can be published, ALL of the following checks must pass:

### 1. Leo Approval Check
- [x] **REQUIRED**: Draft must be explicitly approved by Leo
- [x] **Audit Trail**: Approval is logged with timestamp
- [x] **Verification**: `leo_approved` field must be `True`

### 2. Platform Check
- [x] **VALID PLATFORMS**: google_ads, linkedin, facebook, google_business, email, seo_article
- [x] **INVALID**: Any other platform is rejected

### 3. Landing Page Check
- [x] **REQUIRED**: Must have a valid URL
- [x] **FORMAT**: Must start with `http://` or `https://`
- [x] **NO LOCALHOST**: Production URLs only

### 4. Budget Cap Check
- [x] **WARNING**: Prompts if no budget specified
- [x] **INFO**: Shows when budget cap is set
- [x] **NOT BLOCKING**: Warning only, doesn't prevent publishing

### 5. Sensitive Content Check
- [x] **BLOCKED CONTENT**:
  - "free money", "guaranteed", "no questions asked"
  - "click here now", "limited time offer", "act now"
  - "don't miss", "winner", "prize"
  - "congratulations you won"
  - "your account has been compromised"
  - "urgent action required"
- [x] **ACTION**: Draft is blocked if sensitive content detected

### 6. Exaggeration Check
- [x] **WARNING CONTENT**:
  - "best ever", "number one", "#1", "ranked first"
  - "100% effective", "guaranteed to work"
  - "never fail", "absolute best", "ultimate solution"
  - "perfect for everyone"
- [x] **ACTION**: Warning generated, not blocking

### 7. API Key Leak Detection
- [x] **DETECTED PATTERNS**:
  - `api_key`, `token`, `password`, `secret` with values
  - Bearer tokens
  - OpenAI keys: `sk-...`
  - GitHub tokens: `ghp_...`
  - Google tokens: `AIza...`, `ya29...`
  - Facebook/LinkedIn tokens
- [x] **ACTION**: Draft is BLOCKED if leak detected

### 8. Mock Mode Verification
- [x] **REQUIRED**: Publish must be in mock mode
- [x] **BLOCKED**: Real publish without explicit approval
- [x] **LOGGING**: All attempts logged for audit

---

## 🔐 Approval Workflow

```
┌─────────────┐
│   DRAFT     │  ← Initial status
└──────┬──────┘
       │ Submit for Approval
       ▼
┌──────────────────┐
│ PENDING_REVIEW   │  ← Awaiting reviewer
└──────┬───────────┘
       │
       ├── Approve ──────────────────┐
       │                             │
       │                             ▼
       │                    ┌─────────────┐
       │                    │  APPROVED  │  ← Ready to publish
       │                    └──────┬──────┘
       │                             │
       │                             │ Publish (dry-run)
       │                             ▼
       │                    ┌─────────────┐
       │                    │  PUBLISHED │  ← Mock only
       │                    └─────────────┘
       │
       └── Reject
              │
              ▼
       ┌─────────────┐
       │  REJECTED   │  ← Needs revision
       └─────────────┘
```

---

## 🚨 Emergency Procedures

### If a Draft is Published Accidentally
1. **DO NOT PANIC** - No real ad was published (mock mode)
2. Check the PublishLog for details
3. Verify `mock_mode: true` in the log
4. No financial impact - cost was $0

### If an API Key is Leaked
1. **IMMEDIATELY** rotate the exposed credential
2. Check the draft content that leaked it
3. Delete or revise the draft
4. Review who had access to the draft
5. Update affected systems with new credentials

### If Unauthorized Access is Suspected
1. Check server logs for suspicious activity
2. Review all PublishLog entries
3. Verify session management is working
4. Contact security team if needed

---

## 📊 Monitoring

### Publish Logs
All publish attempts are logged with:
- Timestamp
- User ID
- Draft ID
- Action (safety_check, dry_run, publish, approve, reject)
- Mock mode status
- Cost (always $0 in mock mode)
- Warnings/errors

### Safety Dashboard
Access at `/marketing/reports`:
- Total drafts by status
- Publish action history
- Mock mode compliance
- Cost tracking (always $0)

---

## 🛡️ Security Best Practices

### For Developers
1. **NEVER** commit real API keys to code
2. **ALWAYS** use environment variables
3. **ALWAYS** run safety checks before publish
4. **ALWAYS** enable mock mode first
5. **ALWAYS** test with dry-run before approval

### For Marketing Team
1. **NEVER** share login credentials
2. **ALWAYS** review draft content before approving
3. **ALWAYS** check the safety warnings
4. **NEVER** approve drafts with leaked credentials
5. **ALWAYS** use the approval queue

### For Leo
1. **ONLY** approve drafts you have personally reviewed
2. **CHECK** all safety warnings before approving
3. **VERIFY** the draft content is appropriate
4. **MONITOR** the publish logs regularly
5. **REPORT** any suspicious activity immediately

---

## 📞 Emergency Contacts

| Issue | Contact | Response Time |
|-------|---------|--------------|
| API Key Leaked | security@example.com | Immediate |
| Unauthorized Access | security@example.com | Immediate |
| System Down | tech-support@example.com | 4 hours |
| Billing Questions | billing@example.com | 24 hours |

---

## 🔄 Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-06-15 | 3.0.0 | Initial safety documentation |
| - | - | Added all 8 safety gates |
| - | - | Documented approval workflow |
| - | - | Added emergency procedures |

---

## ⚠️ DISCLAIMER

This system is designed with safety as the top priority. While we strive to prevent all accidents, no system is 100% secure. Always verify the status of critical operations and maintain proper oversight of all marketing activities.

**Current Status**: All real publishing APIs are **DISABLED**. Only mock/dry-run publishing is available. Real API integration requires explicit approval from Leo.
