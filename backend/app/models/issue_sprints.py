from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IssueSprint(Base):
    """Deterministic issue-to-sprint membership from Jira sprint fields."""

    __tablename__ = "issue_sprints"
    __table_args__ = (UniqueConstraint("issue_key", "sprint_id", name="uq_issue_sprints_issue_key_sprint_id"),)

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column(
        "issue_key",
        String(32),
        ForeignKey("issues.issue_key", ondelete="CASCADE"),
        index=True,
    )
    sprint_id: Mapped[str] = mapped_column(
        "sprint_id",
        String(64),
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
