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
