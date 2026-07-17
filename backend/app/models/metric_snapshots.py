from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, event, func
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
    ruleset_version: Mapped[int] = mapped_column("ruleset_version", Integer, nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column("confidence_score", Float, nullable=True)
    confidence_status: Mapped[str | None] = mapped_column("confidence_status", String(32), nullable=True)
    calculation_provenance: Mapped[dict[str, object]] = mapped_column(
        "calculation_provenance", JSON, nullable=False, default=dict
    )
    open_blockers: Mapped[int] = mapped_column("open_blockers", Integer, nullable=False)
    open_high_severity_bugs: Mapped[int] = mapped_column("open_high_severity_bugs", Integer, nullable=False)
    open_blocker_issue_keys: Mapped[list[str]] = mapped_column(
        "open_blocker_issue_keys",
        JSON,
        default=list,
        nullable=False,
    )
    open_high_severity_bug_issue_keys: Mapped[list[str]] = mapped_column(
        "open_high_severity_bug_issue_keys",
        JSON,
        default=list,
        nullable=False,
    )
    scope_completed_pct: Mapped[float] = mapped_column("scope_completed_pct", Float, nullable=False)
    completed_tickets: Mapped[int | None] = mapped_column("completed_tickets", Integer, nullable=True)
    scope_churn_7d_pct: Mapped[float] = mapped_column("scope_churn_7d_pct", Float, nullable=False)
    scope_added_7d_count: Mapped[int] = mapped_column("scope_added_7d_count", Integer, nullable=False, default=0)
    scope_removed_7d_count: Mapped[int] = mapped_column("scope_removed_7d_count", Integer, nullable=False, default=0)
    median_cycle_time_days: Mapped[float | None] = mapped_column("median_cycle_time_days", Float, nullable=True)
    reopen_rate_pct: Mapped[float] = mapped_column("reopen_rate_pct", Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(MetricSnapshot, "before_update")
@event.listens_for(MetricSnapshot, "before_delete")
def _prevent_metric_snapshot_mutation(*_args: object) -> None:
    raise ValueError("Metric snapshots are immutable; create a new snapshot instead.")
