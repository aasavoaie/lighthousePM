import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.session import SessionLocal
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.services.sync_service import SyncService, SyncServiceError
from app.utils.error_sanitizer import sanitize_error_detail

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_sync_job() -> None:
    """Periodic Jira sync job. Runs in the event loop via APScheduler."""
    logger.info("scheduled_sync_started")
    session = SessionLocal()
    try:
        await SyncService().sync_from_jira(session=session)
    except SyncServiceError as exc:
        logger.error("scheduled_sync_failed error=%s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduled_sync_unexpected_error error=%s", exc)
        try:
            OperationalStatusRepository.mark_sync_failed(
                session=session,
                failure_summary=sanitize_error_detail(f"{type(exc).__name__}: {exc}"),
            )
            session.commit()
        except SQLAlchemyError as persist_exc:
            session.rollback()
            logger.warning("scheduled_sync_failure_status_persist_failed error=%s", persist_exc)
    finally:
        session.close()


def start_scheduler(settings: Settings) -> None:
    """Start the background sync scheduler if configured.

    The scheduler is disabled when jira_sync_interval_seconds <= 0.
    To disable in development or testing, set JIRA_SYNC_INTERVAL_SECONDS=0 (the default).
    """
    global _scheduler

    interval = settings.jira_sync_interval_seconds
    if interval <= 0:
        logger.debug("scheduled_sync_disabled interval=%d", interval)
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_sync_job,
        trigger="interval",
        seconds=interval,
        id="jira_sync",
        max_instances=1,   # prevents overlapping runs
        coalesce=True,     # collapse missed fires into one
        misfire_grace_time=30,
    )
    _scheduler.start()
    logger.info("scheduled_sync_scheduler_started interval_seconds=%d", interval)


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully on app shutdown."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduled_sync_scheduler_stopped")
    _scheduler = None
