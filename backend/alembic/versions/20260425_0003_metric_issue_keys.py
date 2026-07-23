"""Persist metric issue-key lists.

Revision ID: 20260425_0003
Revises: 20260424_0002
Create Date: 2026-04-25 00:03:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260425_0003"
down_revision: str | None = "20260424_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metric_snapshots",
        sa.Column("open_blocker_issue_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "metric_snapshots",
        sa.Column("open_high_severity_bug_issue_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("open_blocker_issue_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("open_high_severity_bug_issue_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("sprint_metric_snapshots", "open_high_severity_bug_issue_keys")
    op.drop_column("sprint_metric_snapshots", "open_blocker_issue_keys")
    op.drop_column("metric_snapshots", "open_high_severity_bug_issue_keys")
    op.drop_column("metric_snapshots", "open_blocker_issue_keys")
