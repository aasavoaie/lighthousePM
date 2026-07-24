from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JiraProjectSyncState(Base):
    """Per-project Jira sync cursor derived from authoritative Jira timestamps."""

    __tablename__ = "jira_project_sync_state"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    project_key: Mapped[str] = mapped_column(
        "project_key",
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    last_successful_jira_updated_at: Mapped[datetime | None] = mapped_column(
        "last_successful_jira_updated_at",
        DateTime(timezone=True),
        nullable=True,
    )
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(
        "last_successful_sync_at",
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
