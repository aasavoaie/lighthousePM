"""Add sprint bugs-created metric.

Revision ID: 20260428_0005
Revises: 20260427_0004
Create Date: 2026-04-28 00:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260428_0005"
down_revision: str | None = "20260427_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("bugs_created_during_sprint", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("bugs_created_during_sprint_issue_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("sprint_metric_snapshots", "bugs_created_during_sprint_issue_keys")
    op.drop_column("sprint_metric_snapshots", "bugs_created_during_sprint")
