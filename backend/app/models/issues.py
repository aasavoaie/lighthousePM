from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Issue(Base):
    """Issue snapshot table stub for future Jira ingestion."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column("issue_key", String(32), unique=True, index=True)
    summary: Mapped[str] = mapped_column("summary", Text)
    issue_type: Mapped[str] = mapped_column("issue_type", String(64))
    status: Mapped[str] = mapped_column("status", String(64), index=True)
    priority: Mapped[str | None] = mapped_column("priority", String(64), nullable=True)
    assignee: Mapped[str | None] = mapped_column("assignee", String(128), nullable=True)
    release_id: Mapped[str | None] = mapped_column(
        "release_id",
        String(64),
        ForeignKey("releases.release_id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    is_blocker: Mapped[bool] = mapped_column("is_blocker", Boolean, default=False, nullable=False)
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
