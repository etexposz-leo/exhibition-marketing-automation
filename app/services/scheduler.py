import asyncio
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import ScheduledPost, SocialAccount
from app.services.linkedin_service import get_linkedin_service
from app.services.facebook_service import get_facebook_service
from app.services.google_business_service import get_google_business_service

logger = logging.getLogger(__name__)


class PostScheduler:
    """Background scheduler for auto-publishing posts."""
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the scheduler."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Post scheduler started")
    
    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Post scheduler stopped")
    
    async def _run_scheduler(self):
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_and_publish()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _check_and_publish(self):
        """Check for due posts and publish them."""
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            
            # Find posts that are scheduled and due
            due_posts = db.query(ScheduledPost).filter(
                ScheduledPost.status == "scheduled",
                ScheduledPost.scheduled_at <= now
            ).all()
            
            for post in due_posts:
                await self._publish_post(db, post)
            
            db.commit()
        except Exception as e:
            logger.error(f"Error checking posts: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def _publish_post(self, db: Session, post: ScheduledPost):
        """Publish a single post to the appropriate platform."""
        logger.info(f"Publishing post {post.id} to {post.platform}")
        
        # Get social account if specified
        social_account = None
        if post.social_account_id:
            social_account = db.query(SocialAccount).filter(
                SocialAccount.id == post.social_account_id
            ).first()
        
        # Publish based on platform
        if post.platform == "linkedin":
            result = await self._publish_linkedin(post.content, social_account)
        elif post.platform == "facebook":
            result = await self._publish_facebook(post.content, social_account)
        elif post.platform == "google_business":
            result = await self._publish_google_business(post.content, social_account)
        else:
            result = {"success": False, "error": f"Unknown platform: {post.platform}"}
        
        # Update post status
        if result["success"]:
            post.status = "published"
            post.published_at = datetime.utcnow()
            post.platform_post_id = result.get("post_id")
            logger.info(f"Post {post.id} published successfully")
        else:
            post.status = "failed"
            post.error_message = result.get("error")
            logger.error(f"Post {post.id} failed: {result.get('error')}")
        
        post.updated_at = datetime.utcnow()
    
    async def _publish_linkedin(self, content: str, account: Optional[SocialAccount]) -> dict:
        """Publish to LinkedIn."""
        access_token = None
        if account and account.access_token:
            access_token = account.access_token
        
        service = get_linkedin_service(access_token)
        return await service.post_text(content)
    
    async def _publish_facebook(self, content: str, account: Optional[SocialAccount]) -> dict:
        """Publish to Facebook."""
        access_token = None
        page_id = None
        if account:
            access_token = account.access_token
            page_id = account.account_id
        
        service = get_facebook_service(access_token)
        return await service.post_to_page(content, page_id)
    
    async def _publish_google_business(self, content: str, account: Optional[SocialAccount]) -> dict:
        """Publish to Google Business Profile."""
        api_key = None
        location_id = None
        access_token = None
        if account:
            api_key = account.access_token  # Reusing field for API key
            location_id = account.account_id
            access_token = account.refresh_token  # Reusing for OAuth token
        
        service = get_google_business_service(api_key, access_token)
        return await service.create_local_post(content, location_id)
    
    async def publish_now(self, platform: str, content: str, account_id: Optional[int] = None) -> dict:
        """
        Publish a post immediately.
        
        Args:
            platform: The platform to post to
            content: The post content
            account_id: Optional social account ID to use
            
        Returns:
            dict with success status and post details
        """
        db = SessionLocal()
        try:
            account = None
            if account_id:
                account = db.query(SocialAccount).filter(
                    SocialAccount.id == account_id
                ).first()
            
            # Publish based on platform
            if platform == "linkedin":
                result = await self._publish_linkedin(content, account)
            elif platform == "facebook":
                result = await self._publish_facebook(content, account)
            elif platform == "google_business":
                result = await self._publish_google_business(content, account)
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
            
            return result
        finally:
            db.close()


# Global scheduler instance
scheduler = PostScheduler()


async def start_scheduler():
    """Start the global scheduler."""
    await scheduler.start()


async def stop_scheduler():
    """Stop the global scheduler."""
    await scheduler.stop()
