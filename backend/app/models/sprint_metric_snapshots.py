from datetime import datetime

from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SprintMetricSnapshot(Base):
    """Deterministic sprint metric snapshots over time."""

    __tablename__ = "sprint_metric_snapshots"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    sprint_id: Mapped[str] = mapped_column(
        "sprint_id",
        String(64),
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"),
        index=True,
    )
    snapshot_at: Mapped[datetime] = mapped_column("snapshot_at", DateTime(timezone=True), index=True)
    committed_scope: Mapped[int] = mapped_column("committed_scope", Integer, nullable=False)
    completed_scope_pct: Mapped[float] = mapped_column("completed_scope_pct", Float, nullable=False)
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
    in_progress_count: Mapped[int] = mapped_column("in_progress_count", Integer, nullable=False)
    not_started_count: Mapped[int] = mapped_column("not_started_count", Integer, nullable=False)
    rollover_count: Mapped[int] = mapped_column("rollover_count", Integer, nullable=False)
    median_cycle_time_days: Mapped[float | None] = mapped_column("median_cycle_time_days", Float, nullable=True)
    reopen_rate_pct: Mapped[float] = mapped_column("reopen_rate_pct", Float, nullable=False)
    delivery_confidence_score: Mapped[float | None] = mapped_column(
        "delivery_confidence_score",
        Float,
        nullable=True,
    )
    delivery_confidence_components: Mapped[dict[str, float] | None] = mapped_column(
        "delivery_confidence_components",
        JSON,
        nullable=True,
    )
    delivery_confidence_inputs: Mapped[dict[str, Any] | None] = mapped_column(
        "delivery_confidence_inputs",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
