import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from backend.app.config import get_settings
from backend.app.database.database import SessionLocal
from backend.app.services.publishing_service import PublishingService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

def _run_publisher_tick() -> None:
    """Synchronous worker function executed by the scheduler tick."""
    db = SessionLocal()
    try:
        processed = PublishingService.process_due_posts(db)
        if processed > 0:
            logger.info("Publisher background cycle successfully processed %s due post(s).", processed)
    except Exception as exc:
        logger.error("Error during scheduler due post processing: %s", exc, exc_info=True)
    finally:
        db.close()

async def tick_worker() -> None:
    """Async wrapper delegating to thread pool so DB I/O does not block event loop."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_publisher_tick)

def start_scheduler() -> AsyncIOScheduler | None:
    """Start the APScheduler background worker if enabled."""
    global _scheduler
    settings = get_settings()

    if not getattr(settings, "SCHEDULER_ENABLED", True):
        logger.info("Background scheduler is disabled via configuration.")
        return None

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running.")
        return _scheduler

    interval = getattr(settings, "SCHEDULER_POLL_INTERVAL_SECONDS", 15)
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        tick_worker,
        trigger=IntervalTrigger(seconds=interval),
        id="social_media_publisher_due_scanner",
        name="Poll and publish due social media posts",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("Background publisher scheduler started (poll interval=%ss).", interval)
    return _scheduler

def stop_scheduler() -> None:
    """Stop the APScheduler background worker gracefully."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Background publisher scheduler stopped.")
        except Exception as exc:
            logger.warning("Error stopping scheduler: %s", exc)
        finally:
            _scheduler = None

def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
