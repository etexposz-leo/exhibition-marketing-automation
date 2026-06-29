"""
Safety Gate Service for Marketing Automation

⚠️ IMPORTANT: This module enforces safety checks BEFORE any publish action.

Safety checks include:
1. Leo approval verification
2. Platform existence check
3. Landing page validation
4. Budget cap verification
5. Sensitive content detection
6. Exaggeration detection
7. API key / token / password leak detection
8. Mock mode verification

NO REAL PUBLISHING OCCURS WITHOUT ALL CHECKS PASSING.
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    passed: bool
    check_name: str
    message: str
    severity: str = "error"  # error, warning, info
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SafetyGateResult:
    """Result of the full safety gate check."""
    all_passed: bool
    checks: List[SafetyCheckResult] = field(default_factory=list)
    can_publish: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    summary: str = ""


class SafetyGate:
    """
    Safety Gate for marketing content publishing.
    
    This service MUST be called before ANY publish attempt.
    It checks for:
    - Leo approval
    - Platform existence
    - Landing page validation
    - Budget cap
    - Sensitive content
    - Exaggeration
    - API key leaks
    - Mock mode verification
    """
    
    # Sensitive patterns to detect API keys, tokens, passwords
    API_KEY_PATTERNS = [
        r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{20,}["\']?',
        r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-\.]{20,}["\']?',
        r'password["\']?\s*[:=]\s*["\']?[^"\s]{8,}["\']?',
        r'secret["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{20,}["\']?',
        r'bearer\s+[a-zA-Z0-9_\-\.]+',
        r'sk[-_][a-zA-Z0-9]{20,}',
        r'ghp_[a-zA-Z0-9]{36,}',
        r'AIza[a-zA-Z0-9_\-]{35,}',
        r'ya29\.[a-zA-Z0-9_\-]{100,}',
        r'googledeveloperstoken[a-zA-Z0-9_\-]{50,}',
        r'facebooktoken[a-zA-Z0-9_\-]{50,}',
        r'linkedin[a-zA-Z0-9_\-]{50,}',
    ]
    
    # Sensitive keywords
    SENSITIVE_KEYWORDS = [
        "free money", "guaranteed win", "no questions asked",
        "click here now", "limited time offer", "act now",
        "don't miss", "winner", "prize", "congratulations you won",
        "your account has been compromised", "urgent action required",
        "verify your account now", "confirm your identity"
    ]
    
    # Exaggeration patterns
    EXAGGERATION_PATTERNS = [
        r'best ever', r'number one', r'#1', r'ranked first',
        r'100% effective', r'guaranteed to work', r'never fail',
        r'absolute best', r'ultimate solution', r'perfect for everyone',
        r'will definitely', r'without fail', r'better than all others'
    ]
    
    def __init__(self):
        """Initialize Safety Gate."""
        self.checks_enabled = True
        self.leo_approval_required = True  # Leo MUST approve
        self.mock_mode_required = True  # Mock mode must be enabled
        self.strict_mode = True  # All checks must pass
        
        logger.info("🛡️ SAFETY GATE INITIALIZED")
        logger.info("  - Leo approval required: YES")
        logger.info("  - Mock mode required: YES")
        logger.info("  - Strict mode: ENABLED")
    
    def check_all(
        self, 
        content: Dict, 
        user_approval: Optional[Dict] = None,
        is_mock_mode: bool = True
    ) -> SafetyGateResult:
        """
        Run all safety checks on content.
        
        Args:
            content: The ad draft content
            user_approval: Approval info from Leo
            is_mock_mode: Whether we're in mock/dry-run mode
            
        Returns:
            SafetyGateResult with all check results
        """
        checks = []
        warnings = []
        errors = []
        
        # 1. Mock Mode Check (MUST PASS)
        mock_check = self._check_mock_mode(is_mock_mode)
        checks.append(mock_check)
        if not mock_check.passed:
            errors.append(mock_check.message)
        
        # 2. Leo Approval Check (MUST PASS)
        leo_check = self._check_leo_approval(content, user_approval)
        checks.append(leo_check)
        if not leo_check.passed:
            errors.append(leo_check.message)
        
        # 3. Platform Check (MUST PASS)
        platform_check = self._check_platform(content)
        checks.append(platform_check)
        if not platform_check.passed:
            errors.append(platform_check.message)
        
        # 4. Landing Page Check (MUST PASS)
        landing_check = self._check_landing_page(content)
        checks.append(landing_check)
        if not landing_check.passed:
            errors.append(landing_check.message)
        
        # 5. Budget Check (WARNING only)
        budget_check = self._check_budget(content)
        checks.append(budget_check)
        if not budget_check.passed:
            warnings.append(budget_check.message)
        
        # 6. Sensitive Content Check (MUST PASS)
        sensitive_check = self._check_sensitive_content(content)
        checks.append(sensitive_check)
        if not sensitive_check.passed:
            errors.append(sensitive_check.message)
        
        # 7. Exaggeration Check (WARNING only)
        exaggerate_check = self._check_exaggeration(content)
        checks.append(exaggerate_check)
        if not exaggerate_check.passed:
            warnings.append(exaggerate_check.message)
        
        # 8. API Key Leak Check (MUST PASS)
        api_key_check = self._check_api_key_leak(content)
        checks.append(api_key_check)
        if not api_key_check.passed:
            errors.append(api_key_check.message)
        
        # 9. Schedule Check (INFO)
        schedule_check = self._check_schedule(content)
        checks.append(schedule_check)
        
        all_passed = len(errors) == 0
        can_publish = all_passed and is_mock_mode
        
        result = SafetyGateResult(
            all_passed=all_passed,
            checks=checks,
            can_publish=can_publish,
            warnings=warnings,
            errors=errors,
            summary=self._generate_summary(all_passed, len(checks), warnings, errors)
        )
        
        # Log result
        if all_passed:
            logger.info(f"✅ SAFETY GATE PASSED ({len(checks)} checks)")
        else:
            logger.error(f"❌ SAFETY GATE FAILED - {len(errors)} errors")
            for error in errors:
                logger.error(f"  - {error}")
        
        return result
    
    def _check_mock_mode(self, is_mock_mode: bool) -> SafetyCheckResult:
        """Check if we're in mock/dry-run mode."""
        if is_mock_mode:
            return SafetyCheckResult(
                passed=True,
                check_name="mock_mode",
                message="✅ Mock/Dry-run mode is enabled",
                severity="info"
            )
        else:
            return SafetyCheckResult(
                passed=False,
                check_name="mock_mode",
                message="❌ REAL PUBLISH MODE - Not allowed without explicit approval",
                severity="error",
                details={"real_publish_blocked": True}
            )
    
    def _check_leo_approval(
        self, 
        content: Dict, 
        user_approval: Optional[Dict]
    ) -> SafetyCheckResult:
        """Check if Leo has approved this content."""
        leo_approved = content.get("leo_approved", False)
        
        if leo_approved:
            return SafetyCheckResult(
                passed=True,
                check_name="leo_approval",
                message="✅ Leo has approved this content",
                severity="info",
                details={"approved_by": content.get("approved_by"), "approved_at": content.get("approved_at")}
            )
        else:
            return SafetyCheckResult(
                passed=False,
                check_name="leo_approval",
                message="❌ Leo approval required - Content not yet approved",
                severity="error",
                details={"approval_required": True}
            )
    
    def _check_platform(self, content: Dict) -> SafetyCheckResult:
        """Check if platform is specified and valid."""
        platform = content.get("platform", "")
        
        valid_platforms = [
            "google_ads", "linkedin", "facebook", 
            "google_business", "email", "seo_article"
        ]
        
        if not platform:
            return SafetyCheckResult(
                passed=False,
                check_name="platform",
                message="❌ No platform specified",
                severity="error"
            )
        
        if platform not in valid_platforms:
            return SafetyCheckResult(
                passed=False,
                check_name="platform",
                message=f"❌ Invalid platform: {platform}",
                severity="error",
                details={"valid_platforms": valid_platforms}
            )
        
        return SafetyCheckResult(
            passed=True,
            check_name="platform",
            message=f"✅ Platform valid: {platform}",
            severity="info",
            details={"platform": platform}
        )
    
    def _check_landing_page(self, content: Dict) -> SafetyCheckResult:
        """Check if landing page is specified and valid."""
        landing_page = content.get("landing_page", "")
        
        if not landing_page:
            return SafetyCheckResult(
                passed=False,
                check_name="landing_page",
                message="❌ No landing page URL specified",
                severity="error"
            )
        
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        
        if not url_pattern.match(landing_page):
            return SafetyCheckResult(
                passed=False,
                check_name="landing_page",
                message=f"❌ Invalid landing page URL: {landing_page}",
                severity="error"
            )
        
        return SafetyCheckResult(
            passed=True,
            check_name="landing_page",
            message="✅ Landing page URL is valid",
            severity="info",
            details={"landing_page": landing_page}
        )
    
    def _check_budget(self, content: Dict) -> SafetyCheckResult:
        """Check if budget is specified and has cap."""
        has_budget = content.get("suggested_budget", 0) > 0 or content.get("daily_budget", 0) > 0
        has_cap = content.get("has_budget_cap", False)
        
        if not has_budget:
            return SafetyCheckResult(
                passed=True,  # Budget is optional
                check_name="budget",
                message="ℹ️ No budget specified (will use default)",
                severity="info"
            )
        
        if has_budget and has_cap:
            return SafetyCheckResult(
                passed=True,
                check_name="budget",
                message=f"✅ Budget has cap: ${content.get('suggested_budget', 0)}",
                severity="info"
            )
        
        return SafetyCheckResult(
            passed=False,
            check_name="budget",
            message=f"⚠️ Budget specified but no cap set. Consider adding budget cap.",
            severity="warning",
            details={"budget": content.get("suggested_budget", 0)}
        )
    
    def _check_sensitive_content(self, content: Dict) -> SafetyCheckResult:
        """Check for sensitive/problematic content."""
        text_to_check = self._get_text_content(content)
        text_lower = text_to_check.lower()
        
        found_keywords = []
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword in text_lower:
                found_keywords.append(keyword)
        
        if found_keywords:
            return SafetyCheckResult(
                passed=False,
                check_name="sensitive_content",
                message=f"❌ Sensitive content detected: {', '.join(found_keywords)}",
                severity="error",
                details={"found_keywords": found_keywords}
            )
        
        return SafetyCheckResult(
            passed=True,
            check_name="sensitive_content",
            message="✅ No sensitive content detected",
            severity="info"
        )
    
    def _check_exaggeration(self, content: Dict) -> SafetyCheckResult:
        """Check for exaggerated claims."""
        text_to_check = self._get_text_content(content)
        
        found_exaggerations = []
        for pattern in self.EXAGGERATION_PATTERNS:
            matches = re.findall(pattern, text_to_check, re.IGNORECASE)
            found_exaggerations.extend(matches)
        
        if found_exaggerations:
            return SafetyCheckResult(
                passed=False,
                check_name="exaggeration",
                message=f"⚠️ Exaggerated claims detected: {', '.join(set(found_exaggerations))}",
                severity="warning",
                details={"exaggerations": list(set(found_exaggerations))}
            )
        
        return SafetyCheckResult(
            passed=True,
            check_name="exaggeration",
            message="✅ No exaggerated claims detected",
            severity="info"
        )
    
    def _check_api_key_leak(self, content: Dict) -> SafetyCheckResult:
        """Check for leaked API keys, tokens, passwords."""
        text_to_check = self._get_text_content(content)
        
        found_leaks = []
        for pattern in self.API_KEY_PATTERNS:
            matches = re.findall(pattern, text_to_check, re.IGNORECASE)
            if matches:
                # Mask the sensitive parts
                for match in matches:
                    masked = re.sub(r'[a-zA-Z0-9]{10}$', '***MASKED***', match)
                    found_leaks.append(masked)
        
        if found_leaks:
            return SafetyCheckResult(
                passed=False,
                check_name="api_key_leak",
                message=f"❌ Potential credential leak detected: {len(found_leaks)} pattern(s) found",
                severity="error",
                details={"potential_leaks": found_leaks, "action": "Content BLOCKED from publishing"}
            )
        
        return SafetyCheckResult(
            passed=True,
            check_name="api_key_leak",
            message="✅ No credential leaks detected",
            severity="info"
        )
    
    def _check_schedule(self, content: Dict) -> SafetyCheckResult:
        """Check if schedule is set."""
        schedule_time = content.get("schedule_time")
        
        if schedule_time:
            return SafetyCheckResult(
                passed=True,
                check_name="schedule",
                message=f"✅ Schedule set: {schedule_time}",
                severity="info"
            )
        
        return SafetyCheckResult(
            passed=True,
            check_name="schedule",
            message="ℹ️ No schedule set (immediate publish if approved)",
            severity="info"
        )
    
    def _get_text_content(self, content: Dict) -> str:
        """Extract all text content for checking."""
        parts = [
            content.get("title", ""),
            content.get("body", ""),
            content.get("cta", ""),
            content.get("email_subject", ""),
            content.get("seo_meta_description", ""),
        ]
        return " ".join(str(p) for p in parts if p)
    
    def _generate_summary(
        self, 
        all_passed: bool, 
        total_checks: int,
        warnings: List[str],
        errors: List[str]
    ) -> str:
        """Generate human-readable summary."""
        if all_passed:
            return (
                f"🛡️ SAFETY GATE PASSED ({total_checks} checks)\n"
                f"   Warnings: {len(warnings)}\n"
                f"   Errors: {len(errors)}\n"
                f"   Status: ✅ CAN PUBLISH (in mock mode)"
            )
        else:
            return (
                f"🛡️ SAFETY GATE FAILED ({total_checks} checks)\n"
                f"   Warnings: {len(warnings)}\n"
                f"   Errors: {len(errors)}\n"
                f"   Status: ❌ CANNOT PUBLISH"
            )
    
    def get_safety_status(self) -> Dict[str, Any]:
        """Get current safety gate status."""
        return {
            "enabled": self.checks_enabled,
            "leo_approval_required": self.leo_approval_required,
            "mock_mode_required": self.mock_mode_required,
            "strict_mode": self.strict_mode,
            "all_checks": [
                "leo_approval",
                "platform",
                "landing_page", 
                "budget",
                "sensitive_content",
                "exaggeration",
                "api_key_leak",
                "mock_mode"
            ]
        }


# Global safety gate instance
safety_gate = SafetyGate()


def run_safety_check(
    content: Dict,
    user_approval: Optional[Dict] = None,
    is_mock_mode: bool = True
) -> SafetyGateResult:
    """
    Convenience function to run safety check.
    
    Call this before ANY publish attempt.
    """
    return safety_gate.check_all(content, user_approval, is_mock_mode)


def get_safety_status() -> Dict[str, Any]:
    """Get safety gate status."""
    return safety_gate.get_safety_status()
