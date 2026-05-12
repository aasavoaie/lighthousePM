"""Add blocked_count to sprint metrics.

Revision ID: 20260507_0005
Revises: 20260427_0004
Create Date: 2026-05-07 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260507_0005"
down_revision: str | None = "20260427_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("sprint_metric_snapshots", "blocked_count")
