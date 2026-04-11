from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OperationalStatus


class OperationalStatusRepository:
    """Read/write helpers for singleton operational status markers."""

    @staticmethod
    def get_status(session: Session) -> OperationalStatus:
        status = session.scalar(select(OperationalStatus).order_by(OperationalStatus.id.asc()).limit(1))
        if status is None:
            status = OperationalStatus()
            session.add(status)
            session.flush()
        return status

    @staticmethod
    def get_status_or_none(session: Session) -> OperationalStatus | None:
        return session.scalar(select(OperationalStatus).order_by(OperationalStatus.id.asc()).limit(1))

    @staticmethod
    def mark_sync_succeeded(session: Session) -> None:
        status = OperationalStatusRepository.get_status(session)
        now = datetime.now(UTC)
        status.last_sync_succeeded_at = now
        status.last_sync_failure_summary = None

    @staticmethod
    def mark_sync_failed(session: Session, failure_summary: str) -> None:
        status = OperationalStatusRepository.get_status(session)
        status.last_sync_failed_at = datetime.now(UTC)
        status.last_sync_failure_summary = failure_summary

    @staticmethod
    def mark_metrics_recomputed(session: Session) -> None:
        status = OperationalStatusRepository.get_status(session)
        status.last_metrics_recompute_at = datetime.now(UTC)

    @staticmethod
    def mark_signal_recomputed(session: Session) -> None:
        status = OperationalStatusRepository.get_status(session)
        status.last_signal_recompute_at = datetime.now(UTC)
