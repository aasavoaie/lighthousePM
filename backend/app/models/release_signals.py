from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReleaseSignal(Base):
    """Stored release signal outputs with explicit reasons."""

    __tablename__ = "release_signals"
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "metric_snapshot_id",
            "ruleset_version",
            name="uq_release_signal_snapshot_ruleset",
        ),
    )

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        "release_id",
        String(64),
        ForeignKey("releases.release_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    metric_snapshot_id: Mapped[int | None] = mapped_column(
        "metric_snapshot_id",
        Integer,
        ForeignKey("metric_snapshots.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    ruleset_version: Mapped[int] = mapped_column("ruleset_version", Integer, nullable=False, default=0)
    signal: Mapped[str] = mapped_column("signal", String(16), index=True, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column("confidence_score", Float, nullable=True)
    reasons: Mapped[list[str]] = mapped_column("reasons", JSON, nullable=False)
    reason_details: Mapped[list[dict[str, object]]] = mapped_column(
        "reason_details", JSON, nullable=False, default=list
    )
    release_gates: Mapped[list[dict[str, object]]] = mapped_column(
        "release_gates", JSON, nullable=False, default=list
    )
    readiness_evidence: Mapped[dict[str, object]] = mapped_column(
        "readiness_evidence", JSON, nullable=False, default=dict
    )
    risk_aging_evidence: Mapped[dict[str, object]] = mapped_column(
        "risk_aging_evidence", JSON, nullable=False, default=dict
    )
    calculated_at: Mapped[datetime] = mapped_column(
        "calculated_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


@event.listens_for(ReleaseSignal, "before_update")
@event.listens_for(ReleaseSignal, "before_delete")
def _prevent_release_signal_mutation(*_args: object) -> None:
    raise ValueError("Release signals are immutable; create a new signal result instead.")
