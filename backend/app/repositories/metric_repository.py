from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import MetricSnapshot


class MetricRepository:
    """Read-only queries for metric snapshots."""

    @staticmethod
    def get_latest_snapshot(session: Session, release_id: str) -> MetricSnapshot | None:
        query = (
            select(MetricSnapshot)
            .where(MetricSnapshot.release_id == release_id)
            .order_by(desc(MetricSnapshot.snapshot_at), desc(MetricSnapshot.id))
            .limit(1)
        )
        return session.scalar(query)

    @staticmethod
    def list_snapshots_for_release(
        session: Session,
        release_id: str,
        limit: int = 500,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> list[MetricSnapshot]:
        query = select(MetricSnapshot).where(MetricSnapshot.release_id == release_id)
        if from_at is not None:
            query = query.where(MetricSnapshot.snapshot_at >= from_at)
        if to_at is not None:
            query = query.where(MetricSnapshot.snapshot_at <= to_at)
        query = query.order_by(MetricSnapshot.snapshot_at.asc(), MetricSnapshot.id.asc()).limit(limit)
        return list(session.scalars(query).all())
