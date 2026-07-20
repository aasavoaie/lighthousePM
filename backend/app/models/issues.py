from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Issue(Base):
    """Issue snapshot table stub for future Jira ingestion."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column("issue_key", String(32), unique=True, index=True)
    summary: Mapped[str] = mapped_column("summary", Text)
    issue_type: Mapped[str | None] = mapped_column("issue_type", String(64), nullable=True)
    status: Mapped[str | None] = mapped_column("status", String(64), index=True, nullable=True)
    priority: Mapped[str | None] = mapped_column("priority", String(64), nullable=True)
    assignee: Mapped[str | None] = mapped_column("assignee", String(128), nullable=True)
    jira_assignee_id: Mapped[str | None] = mapped_column(
        "jira_assignee_id", String(128), nullable=True
    )
    story_points: Mapped[float | None] = mapped_column("story_points", Float, nullable=True)
    release_id: Mapped[str | None] = mapped_column(
        "release_id",
        String(64),
        ForeignKey("releases.release_id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    is_blocker: Mapped[bool] = mapped_column("is_blocker", Boolean, default=False, nullable=False)
    jira_created_at: Mapped[datetime | None] = mapped_column(
        "jira_created_at", DateTime(timezone=True), nullable=True
    )
    jira_updated_at: Mapped[datetime | None] = mapped_column(
        "jira_updated_at", DateTime(timezone=True), nullable=True
    )
    jira_blocker_flag: Mapped[bool | None] = mapped_column(
        "jira_blocker_flag", Boolean, nullable=True
    )
    jira_changelog_complete: Mapped[bool] = mapped_column(
        "jira_changelog_complete", Boolean, nullable=False, default=False
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
