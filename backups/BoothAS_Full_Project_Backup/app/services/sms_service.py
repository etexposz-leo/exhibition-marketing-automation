"""
SMS Service for phone verification.
Supports Twilio and Mock providers.
"""
import os
import random
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from abc import ABC, abstractmethod


class SMSProvider(ABC):
    """Abstract base class for SMS providers."""
    
    @abstractmethod
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS to phone number. Returns True on success."""
        pass


class MockSMSProvider(SMSProvider):
    """Mock SMS provider for testing/demo mode."""
    
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Log the SMS instead of sending (mock mode)."""
        # In production, never log actual SMS content
        print(f"[MOCK SMS] To: {phone_number}")
        print(f"[MOCK SMS] Message: {message}")
        return True


class TwilioSMSProvider(SMSProvider):
    """Twilio SMS provider for production use."""
    
    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
    
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS via Twilio."""
        try:
            from twilio.rest import Client
            
            client = Client(self.account_sid, self.auth_token)
            message = client.messages.create(
                body=message,
                from_=self.from_number,
                to=phone_number
            )
            return message.sid is not None
        except Exception as e:
            print(f"Twilio error: {e}")
            return False


def get_sms_provider() -> SMSProvider:
    """Get the configured SMS provider based on environment."""
    if os.environ.get("SMS_MOCK_MODE", "true").lower() == "true":
        return MockSMSProvider()
    else:
        return TwilioSMSProvider()


def generate_verification_code() -> str:
    """Generate a 6-digit verification code."""
    return str(random.randint(100000, 999999))


def hash_code(code: str) -> str:
    """Hash a verification code for secure storage."""
    return hashlib.sha256(code.encode()).hexdigest()


def verify_code(plain_code: str, hashed_code: str) -> bool:
    """Verify a plain code against its hash."""
    return hash_code(plain_code) == hashed_code


# Singleton provider instance
_sms_provider: Optional[SMSProvider] = None


def get_provider() -> SMSProvider:
    """Get or create the SMS provider singleton."""
    global _sms_provider
    if _sms_provider is None:
        _sms_provider = get_sms_provider()
    return _sms_provider