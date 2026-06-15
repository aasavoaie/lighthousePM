"""Add release scope creep count metrics.

Revision ID: 20260430_0007
Revises: 20260429_0006
Create Date: 2026-04-30 00:07:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260430_0007"
down_revision: str | None = "20260429_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metric_snapshots",
        sa.Column("scope_added_7d_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "metric_snapshots",
        sa.Column("scope_removed_7d_count", sa.Integer(), nullable=False, server_default="0"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("metric_snapshots", "scope_added_7d_count", server_default=None)
        op.alter_column("metric_snapshots", "scope_removed_7d_count", server_default=None)


def downgrade() -> None:
    op.drop_column("metric_snapshots", "scope_removed_7d_count")
    op.drop_column("metric_snapshots", "scope_added_7d_count")
