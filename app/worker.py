"""Explicit standalone worker entrypoint; never enabled by web startup in production."""
import asyncio
import os
from app.core.log_safety import install
from app.core import ownership  # Install the same ORM ownership safeguards as the web app.
from app.core.config import enforce_production_config
from app.services.linkedin_channel import LinkedInAdapter
from app.services.platform_adapter import PlatformRegistry, PlatformType
from app.services.scheduler import PostScheduler


async def run():
    if os.getenv('ENABLE_LINKEDIN_WORKER') != 'true':
        raise RuntimeError('Worker requires explicit local operator configuration')
    install()
    enforce_production_config()
    PlatformRegistry.register(PlatformType.LINKEDIN, LinkedInAdapter())
    scheduler = PostScheduler()
    await scheduler.start()
    try:
        await scheduler._task
    finally:
        await scheduler.stop()


if __name__ == '__main__':
    asyncio.run(run())
