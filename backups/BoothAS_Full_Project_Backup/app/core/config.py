"""
Environment validation for production deployment.
Ensures required environment variables are set before starting the application.
"""

import os
import secrets
from typing import Optional


class EnvironmentError(Exception):
    """Raised when required environment variables are missing."""
    pass


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Get an environment variable with validation.
    
    Args:
        key: Environment variable name
        default: Default value if not set
        required: If True, raises error when missing in production
        
    Returns:
        The environment variable value
        
    Raises:
        EnvironmentError: When required variable is missing
    """
    value = os.environ.get(key, default)
    
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Please set it in your .env file or environment."
        )
    
    return value


def validate_production_config() -> dict:
    """
    Validate that all required configuration is present for production.
    
    Returns:
        dict with validation results
        
    Raises:
        EnvironmentError: When required configuration is missing
    """
    results = {
        "is_production": os.environ.get("ENVIRONMENT", "development") == "production",
        "checks": [],
        "passed": True
    }
    
    # Check SECRET_KEY
    secret_key = os.environ.get("SECRET_KEY", "")
    if results["is_production"]:
        if not secret_key or secret_key == "dev-secret-key-change-in-production":
            results["checks"].append({
                "name": "SECRET_KEY",
                "status": "fail",
                "message": "SECRET_KEY must be set to a secure random value in production"
            })
            results["passed"] = False
        elif len(secret_key) < 32:
            results["checks"].append({
                "name": "SECRET_KEY",
                "status": "fail",
                "message": "SECRET_KEY must be at least 32 characters"
            })
            results["passed"] = False
        else:
            results["checks"].append({
                "name": "SECRET_KEY",
                "status": "pass",
                "message": "SECRET_KEY is configured"
            })
    else:
        results["checks"].append({
            "name": "SECRET_KEY",
            "status": "warn" if not secret_key else "pass",
            "message": "Using default (not recommended for production)"
        })
    
    # Check DATABASE_URL
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        results["checks"].append({
            "name": "DATABASE_URL",
            "status": "fail",
            "message": "DATABASE_URL is not set"
        })
        results["passed"] = False
    else:
        results["checks"].append({
            "name": "DATABASE_URL",
            "status": "pass",
            "message": f"Database configured: {db_url.split('://')[0]}"
        })
    
    # Check HTTPS settings in production
    if results["is_production"]:
        https_only = os.environ.get("HTTPS_ONLY", "false").lower() in ("true", "1", "yes")
        if not https_only:
            results["checks"].append({
                "name": "HTTPS_ONLY",
                "status": "warn",
                "message": "HTTPS_ONLY not set - consider enabling for production"
            })
    
    return results


def enforce_production_config() -> None:
    """
    Enforce production configuration.
    Raises EnvironmentError if critical configuration is missing.
    
    Use this at application startup to prevent running in misconfigured state.
    """
    is_production = os.environ.get("ENVIRONMENT", "development") == "production"
    
    if not is_production:
        return
    
    errors = []
    
    # Check SECRET_KEY
    secret_key = os.environ.get("SECRET_KEY", "")
    if not secret_key:
        errors.append("SECRET_KEY is required in production")
    elif secret_key == "dev-secret-key-change-in-production":
        errors.append("SECRET_KEY cannot be the default development value in production")
    elif len(secret_key) < 32:
        errors.append("SECRET_KEY must be at least 32 characters")
    
    # Check DATABASE_URL
    if not os.environ.get("DATABASE_URL"):
        errors.append("DATABASE_URL is required")
    
    if errors:
        error_msg = "\n".join([
            "Production configuration errors:",
            *[f"  - {e}" for e in errors],
            "",
            "Please set the required environment variables before starting.",
            "See .env.example for reference."
        ])
        raise EnvironmentError(error_msg)


def generate_secret_key() -> str:
    """Generate a secure random secret key."""
    return secrets.token_urlsafe(32)


def print_config_status() -> None:
    """Print current configuration status (for debugging)."""
    results = validate_production_config()
    
    print("\n" + "=" * 50)
    print("Configuration Status")
    print("=" * 50)
    print(f"Environment: {'PRODUCTION' if results['is_production'] else 'DEVELOPMENT'}")
    print()
    
    for check in results["checks"]:
        status_icon = {
            "pass": "✅",
            "warn": "⚠️",
            "fail": "❌"
        }.get(check["status"], "?")
        
        print(f"{status_icon} {check['name']}: {check['message']}")
    
    print()
    print("=" * 50)
    
    if not results["passed"]:
        print("⚠️  Configuration has errors - application may not work correctly")
    elif any(c["status"] == "warn" for c in results["checks"]):
        print("⚠️  Configuration has warnings - review recommended")
    else:
        print("✅ Configuration looks good!")
    
    print("=" * 50 + "\n")