from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Sprint(Base):
    """Jira sprint metadata used for sprint-scoped analytics."""

    __tablename__ = "sprints"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    sprint_id: Mapped[str] = mapped_column("sprint_id", String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column("name", String(255), index=True)
    state: Mapped[str] = mapped_column("state", String(32), index=True)
    project_key: Mapped[str] = mapped_column("project_key", String(64), index=True)
    board_id: Mapped[str | None] = mapped_column("board_id", String(64), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column("start_date", DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column("end_date", DateTime(timezone=True), nullable=True)
    complete_date: Mapped[datetime | None] = mapped_column("complete_date", DateTime(timezone=True), nullable=True)
    goal: Mapped[str | None] = mapped_column("goal", Text, nullable=True)
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
