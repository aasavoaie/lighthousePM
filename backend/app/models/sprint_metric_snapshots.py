from datetime import datetime

from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, event, func
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
    ruleset_version: Mapped[int] = mapped_column("ruleset_version", Integer, nullable=False, default=0)
    calculation_provenance: Mapped[dict[str, object]] = mapped_column(
        "calculation_provenance", JSON, nullable=False, default=dict
    )
    committed_scope: Mapped[int | None] = mapped_column("committed_scope", Integer, nullable=True)
    completed_scope_pct: Mapped[float | None] = mapped_column("completed_scope_pct", Float, nullable=True)
    scope_creep_pct: Mapped[float | None] = mapped_column(
        "scope_creep_pct", Float, nullable=True
    )
    scope_creep_status: Mapped[str] = mapped_column(
        "scope_creep_status", String(32), nullable=False, default="NOT_COMPUTED"
    )
    scope_creep_explanations: Mapped[list[str] | None] = mapped_column(
        "scope_creep_explanations", JSON, nullable=True
    )
    scope_creep_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        "scope_creep_evidence", JSON, nullable=True
    )
    open_blockers: Mapped[int] = mapped_column("open_blockers", Integer, nullable=False)
    open_high_severity_bugs: Mapped[int] = mapped_column("open_high_severity_bugs", Integer, nullable=False)
    bugs_created_during_sprint: Mapped[int] = mapped_column(
        "bugs_created_during_sprint",
        Integer,
        nullable=False,
        default=0,
    )
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
    bugs_created_during_sprint_issue_keys: Mapped[list[str]] = mapped_column(
        "bugs_created_during_sprint_issue_keys",
        JSON,
        default=list,
        nullable=False,
    )
    bugs_created_during_sprint_status: Mapped[str] = mapped_column(
        "bugs_created_during_sprint_status", String(32), nullable=False, default="NOT_COMPUTED"
    )
    bugs_created_during_sprint_missing_created_at_issue_keys: Mapped[list[str]] = mapped_column(
        "bugs_created_during_sprint_missing_created_at_issue_keys",
        JSON,
        nullable=False,
        default=list,
    )
    in_progress_count: Mapped[int | None] = mapped_column("in_progress_count", Integer, nullable=True)
    not_started_count: Mapped[int | None] = mapped_column("not_started_count", Integer, nullable=True)
    rollover_count: Mapped[int | None] = mapped_column("rollover_count", Integer, nullable=True)
    median_cycle_time_days: Mapped[float | None] = mapped_column("median_cycle_time_days", Float, nullable=True)
    reopen_rate_pct: Mapped[float | None] = mapped_column("reopen_rate_pct", Float, nullable=True)
    workload_concentration_pct: Mapped[float | None] = mapped_column(
        "workload_concentration_pct", Float, nullable=True
    )
    workload_distribution_status: Mapped[str | None] = mapped_column(
        "workload_distribution_status", String(32), nullable=True
    )
    workload_distribution_explanations: Mapped[list[str] | None] = mapped_column(
        "workload_distribution_explanations", JSON, nullable=True
    )
    workload_distribution_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        "workload_distribution_evidence", JSON, nullable=True
    )
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
    story_point_total_count: Mapped[int] = mapped_column(
        "story_point_total_count", Integer, nullable=False, default=0
    )
    story_point_pointed_count: Mapped[int] = mapped_column(
        "story_point_pointed_count", Integer, nullable=False, default=0
    )
    story_point_unpointed_count: Mapped[int] = mapped_column(
        "story_point_unpointed_count", Integer, nullable=False, default=0
    )
    story_point_coverage_pct: Mapped[float] = mapped_column(
        "story_point_coverage_pct", Float, nullable=False, default=0.0
    )
    story_point_unpointed_issue_keys: Mapped[list[str]] = mapped_column(
        "story_point_unpointed_issue_keys", JSON, nullable=False, default=list
    )
    delivery_confidence_status: Mapped[str] = mapped_column(
        "delivery_confidence_status", String(32), nullable=False, default="NOT_COMPUTED"
    )
    delivery_confidence_explanations: Mapped[list[str]] = mapped_column(
        "delivery_confidence_explanations", JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(SprintMetricSnapshot, "before_update")
@event.listens_for(SprintMetricSnapshot, "before_delete")
def _prevent_sprint_metric_snapshot_mutation(*_args: object) -> None:
    raise ValueError("Sprint metric snapshots are immutable; create a new snapshot instead.")
