from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReleaseSignal(Base):
    """Stored release signal outputs with explicit reasons."""

    __tablename__ = "release_signals"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        "release_id",
        String(64),
        ForeignKey("releases.release_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    signal: Mapped[str] = mapped_column("signal", String(16), index=True, nullable=False)
    reasons: Mapped[list[str]] = mapped_column("reasons", JSON, nullable=False)
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
