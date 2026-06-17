"""
Authentication utilities using bcrypt and session management.
"""

import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.models import User, Campaign, GeneratedContent, ScheduledPost, SEOKeyword, Competitor


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_user(db: Session, email: str, username: str, password: str, company_name: str = None, is_demo: bool = False) -> User:
    """Create a new user with hashed password."""
    hashed_pw = hash_password(password)
    user = User(
        email=email,
        username=username,
        hashed_password=hashed_pw,
        company_name=company_name,
        is_demo=is_demo,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate a user by email and password."""
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get user by ID."""
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email."""
    return db.query(User).filter(User.email == email).first()


def create_demo_account(db: Session) -> User:
    """Create demo account if it doesn't exist."""
    existing = get_user_by_email(db, "demo@example.com")
    if existing:
        # Mark as phone verified for demo
        if not existing.phone_verified:
            existing.phone_verified = True
            existing.sms_verified_at = datetime.utcnow()
            db.commit()
        return existing
    
    user = create_user(
        db=db,
        email="demo@example.com",
        username="Demo User",
        password="demo123",
        company_name="Exhibition Design Co.",
        is_demo=True
    )
    
    # Mark as phone verified for demo
    user.phone_verified = True
    user.sms_verified_at = datetime.utcnow()
    
    # Create demo data
    create_demo_data(db, user.id)
    
    return user


def create_demo_data(db: Session, user_id: int):
    """Create demo campaigns and scheduled posts for a user."""
    import json
    
    # Demo campaign 1
    campaign1 = Campaign(
        user_id=user_id,
        customer_industry="Technology",
        exhibition_name="CES 2026",
        status="completed"
    )
    db.add(campaign1)
    db.commit()
    db.refresh(campaign1)
    
    # Demo content for campaign 1
    demo_contents = [
        ("linkedin", f"🚀 Join us at CES 2026! Visit our booth to experience the future of exhibition design.\n\nExhibition Design Co. will showcase innovative booth solutions that transform how brands connect with their audience.\n\n#CES2026 #ExhibitionDesign #Innovation"),
        ("facebook", f"🎉 We're heading to CES 2026!\n\nCome visit our booth at the Las Vegas Convention Center and discover cutting-edge exhibition solutions. Our team can't wait to meet you!"),
        ("google_business", "Visit us at CES 2026 - Las Vegas Convention Center. Innovative exhibition solutions for modern brands."),
        ("image_prompt", "Modern exhibition booth design with holographic displays and interactive touchscreens at tech conference\n---\nSleek exhibition booth with LED lighting and sustainable materials at technology trade show\n---\nFuturistic exhibition design featuring AR experiences and modular displays at CES 2026")
    ]
    
    for content_type, content in demo_contents:
        gc = GeneratedContent(
            user_id=user_id,
            campaign_id=campaign1.id,
            content_type=content_type,
            content=content
        )
        db.add(gc)
    
    # Demo campaign 2
    campaign2 = Campaign(
        user_id=user_id,
        customer_industry="Healthcare",
        exhibition_name="Medica 2026",
        status="scheduled"
    )
    db.add(campaign2)
    db.commit()
    db.refresh(campaign2)
    
    # Demo scheduled posts
    scheduled_posts = [
        ScheduledPost(
            user_id=user_id,
            campaign_id=campaign1.id,
            platform="linkedin",
            content="We're live at CES 2026! 🚀 Visit booth #12345 to see our latest exhibition innovations.",
            status="published",
            published_at=datetime.utcnow() - timedelta(days=1),
            is_mock=True
        ),
        ScheduledPost(
            user_id=user_id,
            campaign_id=campaign2.id,
            platform="linkedin",
            content="Excited to announce our participation at Medica 2026! 🏥 Visit us at Hall 13, Booth A42.",
            status="scheduled",
            scheduled_at=datetime.utcnow() + timedelta(days=30),
            is_mock=True
        ),
        ScheduledPost(
            user_id=user_id,
            campaign_id=campaign2.id,
            platform="facebook",
            content="Medica 2026 is coming! Discover how Exhibition Design Co. creates impactful healthcare exhibition spaces.",
            status="scheduled",
            scheduled_at=datetime.utcnow() + timedelta(days=31),
            is_mock=True
        )
    ]
    
    for post in scheduled_posts:
        db.add(post)
    
    # Demo SEO keywords
    demo_keywords = [
        SEOKeyword(
            user_id=user_id,
            keyword="exhibition booth design company",
            target_url="https://www.et-expo.com/services/booth-design",
            category="service",
            priority="high",
            search_volume=1200
        ),
        SEOKeyword(
            user_id=user_id,
            keyword="trade show booth builder USA",
            target_url="https://www.et-expo.com/services/trade-show-booths",
            category="service",
            priority="high",
            search_volume=880
        ),
        SEOKeyword(
            user_id=user_id,
            keyword="CES booth design",
            target_url="https://www.et-expo.com/portfolio/ces-2026",
            category="event",
            priority="medium",
            search_volume=590
        ),
        SEOKeyword(
            user_id=user_id,
            keyword="Las Vegas exhibit builder",
            target_url="https://www.et-expo.com/locations/las-vegas",
            category="location",
            priority="medium",
            search_volume=720
        ),
        SEOKeyword(
            user_id=user_id,
            keyword="custom exhibition booth design",
            target_url="https://www.et-expo.com/services/custom-booths",
            category="service",
            priority="high",
            search_volume=950
        )
    ]
    
    for keyword in demo_keywords:
        db.add(keyword)
    
    # Demo competitors
    demo_competitors = [
        Competitor(
            user_id=user_id,
            name="Skyline Exhibits",
            website="https://www.skylineehibits.com"
        ),
        Competitor(
            user_id=user_id,
            name="Freeman",
            website="https://www.freeman.com"
        ),
        Competitor(
            user_id=user_id,
            name="GES",
            website="https://www.ges.com"
        ),
        Competitor(
            user_id=user_id,
            name="Nimlok",
            website="https://www.nimlok.com"
        ),
        Competitor(
            user_id=user_id,
            name="ExpoMarketing",
            website="https://www.expomarketing.com"
        )
    ]
    
    for competitor in demo_competitors:
        db.add(competitor)
    
    db.commit()
