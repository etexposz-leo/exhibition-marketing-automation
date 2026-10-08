"""Retired compatibility module. All execution belongs to scheduler.py.

Old callers must supply owner context and use publishing.prepare_post with the
request transaction. Importing this module never starts a second worker.
"""
from app.services.scheduler import scheduler

class RetiredScheduler:
    def __getattr__(self, name):
        raise RuntimeError('Legacy scheduler retired; use canonical owner-scoped publishing API')

scheduler_service = RetiredScheduler()
