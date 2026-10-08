"""Canonical durable DB poller. Persisted claims and bounded safe retries."""
import asyncio
import logging
from app.core.database import SessionLocal
from app.core.security import utcnow
from app.models.models import ScheduledPost
from app.services.publishing import process_post
from sqlalchemy import or_, and_
from datetime import timedelta

logger = logging.getLogger(__name__)

class PostScheduler:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory
        self._running = False
        self._task = None

    async def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_scheduler())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_scheduler(self):
        while self._running:
            try:
                await self._check_and_publish()
            except Exception:
                logger.error('Scheduler operation failed; diagnostics withheld')
            await asyncio.sleep(60)

    async def _check_and_publish(self):
        with self.session_factory() as db:
            # A process crash has an unknown provider outcome. Never auto-requeue.
            db.query(ScheduledPost).filter(ScheduledPost.status=='processing',
                ScheduledPost.last_attempt_at < utcnow()-timedelta(minutes=5)).update({
                    'status':'reconciliation_required','error_message':'Interrupted execution; reconcile before any new job'})
            db.commit()
            ids = [row[0] for row in db.query(ScheduledPost.id).filter(or_(
                and_(ScheduledPost.status=='scheduled',ScheduledPost.scheduled_at<=utcnow()),
                and_(ScheduledPost.status=='failed_retryable',ScheduledPost.next_retry_at<=utcnow()))).all()]
        for ident in ids:
            with self.session_factory() as db:
                post=db.query(ScheduledPost).filter_by(id=ident).first()
                if not post:
                    continue
                db.info['owner_id']=post.user_id
                await process_post(db,post,allowed=('scheduled','failed_retryable'))

scheduler = PostScheduler()

async def start_scheduler():
    await scheduler.start()

async def stop_scheduler():
    await scheduler.stop()
