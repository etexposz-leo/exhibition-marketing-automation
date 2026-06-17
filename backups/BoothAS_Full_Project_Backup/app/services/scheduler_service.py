"""
Simple Scheduler Service using APScheduler

Handles scheduling and publishing of posts at specified times.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from app.models.models import ScheduledPost

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Simple scheduler for publishing posts at scheduled times.
    
    Uses APScheduler for job scheduling with memory job store.
    """
    
    _instance = None
    _scheduler: Optional[BackgroundScheduler] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._scheduler is None:
            self._scheduler = BackgroundScheduler(
                jobstores={'default': MemoryJobStore()},
                job_defaults={
                    'coalesce': True,
                    'max_instances': 3,
                    'misfire_grace_time': 60 * 5  # 5 minutes grace time
                }
            )
            self._scheduler.start()
            logger.info("Scheduler service started")
    
    def schedule_post(self, post_id: int, scheduled_time: datetime) -> bool:
        """
        Schedule a post for publishing at the specified time.
        
        Args:
            post_id: ID of the ScheduledPost in database
            scheduled_time: When to publish the post
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        if scheduled_time <= datetime.utcnow():
            logger.warning(f"Scheduled time is in the past for post {post_id}")
            return False
        
        job_id = f"post_{post_id}"
        
        # Remove existing job if any
        self.cancel_post(post_id)
        
        try:
            # Add the job
            self._scheduler.add_job(
                func=self._publish_scheduled_post,
                trigger=DateTrigger(run_date=scheduled_time),
                id=job_id,
                args=[post_id],
                replace_existing=True
            )
            
            # Update post status in database
            db = SessionLocal()
            try:
                post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
                if post:
                    post.status = "scheduled"
                    post.scheduled_at = scheduled_time
                    db.commit()
                    logger.info(f"Post {post_id} scheduled for {scheduled_time}")
                    return True
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to schedule post {post_id}: {e}")
            return False
        
        return False
    
    def cancel_post(self, post_id: int) -> bool:
        """
        Cancel a scheduled post.
        
        Args:
            post_id: ID of the ScheduledPost
            
        Returns:
            True if cancelled successfully
        """
        job_id = f"post_{post_id}"
        
        try:
            job = self._scheduler.get_job(job_id)
            if job:
                self._scheduler.remove_job(job_id)
                logger.info(f"Post {post_id} cancelled")
                
                # Update status in database
                db = SessionLocal()
                try:
                    post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
                    if post:
                        post.status = "draft"
                        db.commit()
                finally:
                    db.close()
                    
                return True
        except Exception as e:
            logger.error(f"Failed to cancel post {post_id}: {e}")
        
        return False
    
    def _publish_scheduled_post(self, post_id: int):
        """
        Internal method to publish a scheduled post.
        
        This is called by APScheduler at the scheduled time.
        """
        logger.info(f"Publishing scheduled post {post_id}")
        
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
            if not post:
                logger.error(f"Post {post_id} not found")
                return
            
            if post.status == "cancelled":
                logger.info(f"Post {post_id} was cancelled, skipping")
                return
            
            # Update status to publishing
            post.status = "publishing"
            db.commit()
            
            # Publish using platform adapter
            from app.services.platform_adapter import get_platform_adapter
            
            try:
                adapter = get_platform_adapter(post.platform)
                result = adapter.publish_sync(post.content)  # Synchronous version
                
                if result.success:
                    post.status = "published"
                    post.published_at = datetime.utcnow()
                    post.platform_post_id = result.post_id
                    post.url = result.url
                    post.is_mock = result.is_mock
                    logger.info(f"Post {post_id} published successfully: {result.post_id}")
                else:
                    post.status = "failed"
                    post.error_message = result.error
                    logger.error(f"Post {post_id} failed: {result.error}")
                    
            except Exception as e:
                post.status = "failed"
                post.error_message = str(e)
                logger.error(f"Post {post_id} error: {e}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error publishing post {post_id}: {e}")
        finally:
            db.close()
    
    def publish_now(self, post_id: int) -> bool:
        """
        Publish a post immediately.
        
        Args:
            post_id: ID of the ScheduledPost
            
        Returns:
            True if published successfully
        """
        # Cancel any scheduled job
        self.cancel_post(post_id)
        
        # Publish immediately
        self._publish_scheduled_post(post_id)
        return True
    
    def get_pending_posts(self):
        """Get all pending scheduled posts."""
        db = SessionLocal()
        try:
            posts = db.query(ScheduledPost).filter(
                ScheduledPost.status.in_(["scheduled", "draft"])
            ).order_by(ScheduledPost.scheduled_at.asc()).all()
            return posts
        finally:
            db.close()
    
    def reschedule_missed_posts(self):
        """
        Reschedule any posts that were missed while the server was down.
        
        This should be called on server startup.
        """
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            missed_posts = db.query(ScheduledPost).filter(
                ScheduledPost.status == "scheduled",
                ScheduledPost.scheduled_at <= now
            ).all()
            
            for post in missed_posts:
                # Publish missed posts immediately
                self._publish_scheduled_post(post.id)
                
        finally:
            db.close()
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown()
            logger.info("Scheduler service stopped")


# Global scheduler instance
scheduler_service = SchedulerService()