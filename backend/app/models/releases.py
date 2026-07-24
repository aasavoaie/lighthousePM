from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Release(Base):
    """Release metadata table stub for deterministic analytics."""

    __tablename__ = "releases"

    id: Mapped[int] = mapped_column("id", primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column("release_id", String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column("name", String(255), index=True)
    project_key: Mapped[str] = mapped_column("project_key", String(64), index=True)
    description: Mapped[str | None] = mapped_column("description", Text, nullable=True)
    status: Mapped[str | None] = mapped_column("status", String(64), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column("start_date", DateTime(timezone=True), nullable=True)
    release_date: Mapped[datetime | None] = mapped_column("release_date", DateTime(timezone=True), nullable=True)
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
