from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IssueHistory(Base):
    """Issue field/status change history for deterministic auditability."""

    __tablename__ = "issue_history"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column(
        "issue_key",
        String(32),
        ForeignKey("issues.issue_key", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column("field_name", String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column("old_value", Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column("new_value", Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column("changed_at", DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
