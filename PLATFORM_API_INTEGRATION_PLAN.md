# Platform API Integration Plan

## ⚠️ IMPORTANT: Currently Disabled

**Status**: All real API integrations are **DISABLED** until explicit approval from Leo.

This document outlines the plan for future real API integration with marketing platforms.

---

## 🚫 Current Implementation

### Mock Publishers Only
All publishing is done through mock publishers that:
- Log actions without making API calls
- Return fake post IDs
- Record $0 cost
- Never reach real platforms

### Platform Support Matrix

| Platform | Mock Support | Real API | Status |
|----------|-------------|----------|--------|
| Google Ads | ✅ Complete | ❌ Not Connected | DISABLED |
| LinkedIn | ✅ Complete | ❌ Not Connected | DISABLED |
| Facebook/Meta | ✅ Complete | ❌ Not Connected | DISABLED |
| Google Business | ✅ Complete | ❌ Not Connected | DISABLED |
| Email | ✅ Complete | ❌ Not Connected | DISABLED |
| SEO Article | ✅ Complete | ❌ Not Connected | DISABLED |

---

## 📋 Future Integration Requirements

### Google Ads Integration

#### Prerequisites
- [ ] Leo's explicit written approval
- [ ] Google Ads API credentials (separate from other Google services)
- [ ] MCC (My Client Center) account access
- [ ] Budget approval for ad spend
- [ ] Campaign naming convention approved
- [ ] Target cost-per-click defined

#### API Details
```
API: Google Ads API v17
Endpoint: https://googleads.googleapis.com
Auth: OAuth 2.0 Service Account
Rate Limit: 10,000 requests/day
```

#### Safety Measures Before Integration
1. Budget cap must be set per campaign
2. Daily spend limit must be configured
3. Emergency stop procedure documented
4. Cost alerting configured
5. Approval workflow must be enforced

#### Implementation Steps
```python
# Step 1: Environment Setup
GOOGLE_ADS_DEVELOPER_TOKEN=xxx
GOOGLE_ADS_CLIENT_ID=xxx
GOOGLE_ADS_CLIENT_SECRET=xxx
GOOGLE_ADS_REFRESH_TOKEN=xxx
GOOGLE_ADS_LOGIN_CUSTOMER_ID=xxx

# Step 2: Enable in settings UI
# User must explicitly enable Google Ads

# Step 3: Run in hybrid mode
# - First 10 campaigns: dry-run + manual approval
# - Review metrics
# - Then enable auto-approve with limits
```

---

### LinkedIn Marketing API Integration

#### Prerequisites
- [ ] Leo's explicit written approval
- [ ] LinkedIn Marketing Developer Application
- [ ] Company Page admin access
- [ ] Ad account access
- [ ] Budget approval

#### API Details
```
API: LinkedIn Marketing API v202401
Endpoint: https://api.linkedin.com/v2
Auth: OAuth 2.0
Rate Limit: Varies by endpoint
Products: Sponsored Content, Lead Gen, Message Ads
```

#### Safety Measures Before Integration
1. Content review workflow mandatory
2. Image/creative approval required
3. Audience targeting limits defined
4. Spend limits per campaign
5. Geographic restrictions

---

### Meta/Facebook Marketing API Integration

#### Prerequisites
- [ ] Leo's explicit written approval
- [ ] Facebook Business Manager account
- [ ] Ad account with payment method
- [ ] Page admin access
- [ ] Pixel/SDK installation (optional)

#### API Details
```
API: Meta Marketing API v19.0
Endpoint: https://graph.facebook.com/v19.0
Auth: System User Access Token
Rate Limit: Varies by endpoint
Products: Ads, Pages, Instagram, Messenger
```

#### Safety Measures Before Integration
1. Ad review process documented
2. Content policy compliance check
3. Budget caps per ad set
4. Audience size limits
5. Geographic targeting restrictions

---

### Google Business Profile API Integration

#### Prerequisites
- [ ] Leo's explicit written approval
- [ ] Google Business Profile verified
- [ ] Location access configured
- [ ] API project with Business Profile enabled

#### API Details
```
API: Business Profile API
Endpoint: https://businessprofile.googleapis.com/v1
Auth: OAuth 2.0 Service Account
Rate Limit: TBD
Products: Posts, Reviews, Q&A
```

#### Safety Measures Before Integration
1. Post frequency limits
2. Content guidelines documented
3. Image/brand compliance check
4. Location verification

---

### Email Marketing Integration

#### Prerequisites
- [ ] Leo's explicit written approval
- [ ] Email service provider account (SendGrid, Mailchimp, etc.)
- [ ] Email list with consent
- [ ] SPF/DKIM configured
- [ ] Unsubscribe process in place

#### Supported Providers
- SendGrid
- Mailchimp
- Amazon SES
- Postmark
- Custom SMTP

#### Safety Measures Before Integration
1. List hygiene process
2. Unsubscribe handling
3. Bounce management
4. Spam score check
5. CAN-SPAM compliance

---

## 🔐 Security Requirements for All APIs

### Credential Management
```python
# NEVER do this:
api_key = "sk_live_xxxx"  # ❌ HARDCODED

# ALWAYS do this:
api_key = os.environ.get("LINKEDIN_ACCESS_TOKEN")  # ✅ ENV VAR
```

### Environment Variables Required
```bash
# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=

# LinkedIn
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_AD_ACCOUNT_ID=
LINKEDIN_COMPANY_ID=

# Meta/Facebook
META_ACCESS_TOKEN=
META_AD_ACCOUNT_ID=
META_PIXEL_ID=

# Google Business
GOOGLE_BUSINESS_API_KEY=
GOOGLE_BUSINESS_ACCOUNT_ID=

# Email
EMAIL_API_KEY=
EMAIL_FROM_ADDRESS=
EMAIL_PROVIDER=sendgrid|mailchimp|ses
```

### Token Storage
- [ ] Tokens stored encrypted at rest
- [ ] Tokens never logged
- [ ] Tokens rotated regularly
- [ ] Tokens revoked on employee departure
- [ ] Audit log of token usage

---

## 📊 Integration Checklist

### Before Any Integration
- [ ] Leo's written approval obtained
- [ ] Budget limits defined and documented
- [ ] Emergency stop procedure created
- [ ] Team trained on safety procedures
- [ ] Test campaigns completed in mock mode
- [ ] Metrics reviewed for 1 week minimum

### Per-Platform Checklist
1. [ ] Prerequisites verified
2. [ ] API credentials secured
3. [ ] Rate limits configured
4. [ ] Cost alerts set up
5. [ ] Approval workflow enabled
6. [ ] Mock mode tested successfully
7. [ ] Dry-run mode tested successfully
8. [ ] First real campaign approved by Leo
9. [ ] Post-campaign review completed

---

## 🧪 Testing Procedures

### Phase 1: Mock Mode (Current)
- [x] All platforms work in mock mode
- [x] Safety gates functional
- [x] Approval workflow tested
- [ ] Load testing completed

### Phase 2: Dry-Run Mode (After Leo Approval)
- [ ] Connect to sandbox APIs
- [ ] Test full workflow with fake data
- [ ] Verify logging and audit trail
- [ ] Performance testing

### Phase 3: Limited Production (After Extensive Testing)
- [ ] Enable single platform
- [ ] Small budget only ($100 max)
- [ ] Daily review for first month
- [ ] Gradual increase based on metrics

### Phase 4: Full Production (After 3-Month Trial)
- [ ] All safety measures verified
- [ ] Team comfortable with process
- [ ] Metrics meeting expectations
- [ ] Leo's final approval

---

## 📞 Approval Request Process

To request API integration:

1. **Open Ticket**: Create issue with:
   - Platform name
   - Business justification
   - Proposed budget
   - Expected timeline

2. **Security Review**: Technical review of:
   - Credential handling
   - Rate limiting
   - Cost controls
   - Safety measures

3. **Leo Approval**: Written approval from Leo:
   - Budget limits
   - Use cases approved
   - Timeline
   - Conditions

4. **Implementation**: Technical team:
   - Configure credentials
   - Enable platform
   - Test thoroughly
   - Document process

5. **Go-Live**: After successful testing:
   - Enable production mode
   - Set up monitoring
   - Schedule daily review

---

## 🚨 Emergency Shutdown

If issues occur during integration:

### Immediate Actions
1. Disable platform in settings UI
2. Pause all campaigns via platform console
3. Review logs for affected drafts
4. Document incident

### Contact Information
| Platform | Emergency Contact |
|----------|------------------|
| Google Ads | Google Ads Support |
| LinkedIn | LinkedIn Marketing Support |
| Meta | Meta Business Support |
| Email Provider | Respective support |

---

## 📝 Change Log

| Date | Platform | Changes | Approved By |
|------|---------|---------|-------------|
| 2026-06-15 | All | Initial plan created | System |
| - | - | Mock mode implemented | - |
| - | - | Safety gates added | - |
| - | All | Real APIs remain disabled | Leo (Pending) |

---

## ⚠️ DISCLAIMER

**NO REAL API INTEGRATION WILL BE ENABLED WITHOUT EXPLICIT APPROVAL FROM LEO.**

Current system operates in mock-only mode. All publish actions are logged and no real ads are sent to any platform.

To enable real API integration, a formal approval process must be completed.
