from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationalStatus(Base):
    """Singleton-style table storing latest operational sync/recompute markers."""

    __tablename__ = "operational_status"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    last_sync_succeeded_at: Mapped[datetime | None] = mapped_column(
        "last_sync_succeeded_at",
        DateTime(timezone=True),
        nullable=True,
    )
    last_sync_failed_at: Mapped[datetime | None] = mapped_column(
        "last_sync_failed_at",
        DateTime(timezone=True),
        nullable=True,
    )
    last_sync_failure_summary: Mapped[str | None] = mapped_column(
        "last_sync_failure_summary",
        String(500),
        nullable=True,
    )
    last_metrics_recompute_at: Mapped[datetime | None] = mapped_column(
        "last_metrics_recompute_at",
        DateTime(timezone=True),
        nullable=True,
    )
    last_signal_recompute_at: Mapped[datetime | None] = mapped_column(
        "last_signal_recompute_at",
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
