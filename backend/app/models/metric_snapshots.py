from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricSnapshot(Base):
    """Deterministic release metric snapshots over time."""

    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        "release_id",
        String(64),
        ForeignKey("releases.release_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column("snapshot_at", DateTime(timezone=True), index=True, nullable=False)
    open_blockers: Mapped[int] = mapped_column("open_blockers", Integer, nullable=False)
    open_high_severity_bugs: Mapped[int] = mapped_column("open_high_severity_bugs", Integer, nullable=False)
    scope_completed_pct: Mapped[float] = mapped_column("scope_completed_pct", Float, nullable=False)
    scope_churn_7d_pct: Mapped[float] = mapped_column("scope_churn_7d_pct", Float, nullable=False)
    median_cycle_time_days: Mapped[float | None] = mapped_column("median_cycle_time_days", Float, nullable=True)
    reopen_rate_pct: Mapped[float] = mapped_column("reopen_rate_pct", Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
